"""MCP adapter (v0.3): thin mapping from MCP tool calls to AgentAction.

The adapter NEVER decides security itself. It normalizes, then the single
PolicyEngine decides, then the runtime runs. On DENY/APPROVAL the underlying
tool implementation is never invoked (killer invariant).
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict

from .actions import AgentAction, execute, normalize
from .approval import ApprovalNeeded, ApprovalStore
from .audit import log_event
from .policy import PolicyEngine, redact
from .sandbox import GuardedSandbox


def _need(args: Dict[str, Any], *keys: str) -> None:
    for k in keys:
        if k not in args or args[k] in (None, ""):
            raise ValueError(f"Malformed MCP request: missing argument {k!r} (fail-closed)")


def to_action(tool: str, arguments: Dict[str, Any], agent_id: str = "mcp-agent") -> AgentAction:
    """Map MCP tool -> AgentAction. Unknown tools and bad args fail closed."""
    args = dict(arguments or {})
    if tool in ("filesystem.read", "fs.read"):
        _need(args, "path")
        return normalize("READ", str(args["path"]), agent_id=agent_id, protocol="mcp", tool=tool)
    if tool in ("filesystem.write", "fs.write"):
        _need(args, "path", "content")
        return normalize("WRITE", str(args["path"]), [str(args["content"])],
                         agent_id=agent_id, protocol="mcp", tool=tool)
    if tool in ("shell.execute", "shell.exec", "exec"):
        _need(args, "command")
        cmd = args["command"]
        if isinstance(cmd, list):
            if not cmd:
                raise ValueError("Malformed MCP request: empty command (fail-closed)")
            return normalize("EXEC", str(cmd[0]), [str(x) for x in cmd[1:]],
                             agent_id=agent_id, protocol="mcp", tool=tool)
        return normalize("EXEC", str(cmd), agent_id=agent_id, protocol="mcp", tool=tool)
    if tool in ("http.request", "http.fetch", "network.request"):
        _need(args, "url")
        return normalize("NETWORK", str(args["url"]), agent_id=agent_id, protocol="mcp", tool=tool)
    raise ValueError(f"Unknown MCP tool {tool!r} (fail-closed)")


class MCPGateway:
    """Intercepts MCP tool invocations. registry maps tool-name -> callable."""

    def __init__(self, engine: PolicyEngine, sandbox: GuardedSandbox,
                 registry: dict[str, Callable[[AgentAction], Any]] | None = None,
                 approvals: ApprovalStore | None = None):
        self.engine = engine
        self.sandbox = sandbox
        self.registry = registry or default_registry(sandbox)
        self.approvals = approvals or ApprovalStore()

    def _log(self, a: AgentAction, d, result: str) -> None:
        from .audit import redact_resource
        log_event(a.action, redact_resource(a.resource), result, d.reason,
                  kind=a.action.lower(), risk=d.risk, log_path=self.sandbox.log_path,
                  agent_id=a.agent_id, protocol=a.protocol, tool=a.tool,
                  request_id=a.request_id)

    def handle(self, tool: str, arguments: dict[str, Any], agent_id: str = "mcp-agent") -> Any:
        from .actions import decide
        act = to_action(tool, arguments, agent_id)
        d = decide(self.engine, act)
        result = "ALLOWED" if d.allowed else "BLOCKED"
        if d.needs_approval:
            result = "APPROVAL"
        self._log(act, d, result)
        if not d.allowed:
            raise PermissionError(f"AGENTGUARD BLOCKED {act.describe()}: {d.reason}")
        if d.needs_approval:
            self.approvals.request(act, d.reason)
            raise ApprovalNeeded(act.request_id, act.describe())
        return self._run(tool, act)

    def _run(self, tool: str, act: AgentAction, preapproved: bool = False) -> Any:
        impl = self.registry.get(tool)
        if impl is None:
            raise ValueError(f"No implementation for tool {tool!r} (fail-closed)")
        if preapproved and tool in ("shell.execute", "shell.exec", "exec"):
            return self._run_approved(act)
        return impl(act)

    def _run_approved(self, act: AgentAction) -> Any:
        """Post-approval exec: human cleared the approval gate; deny/resource
        gates stay enforced inside run_command."""
        cmd = [act.resource, *act.args] if act.args else act.resource
        r = self.sandbox.run_command(cmd, preapproved=True)
        return r.stdout

    def complete(self, request_id: str, approved: bool, by: str = "human") -> Any:
        """Human decision on a queued request. DENY never runs the tool."""
        from .actions import decide, normalize
        rec = self.approvals.decide(request_id, approved, by)
        act = normalize(rec["action"], rec["resource"], rec["args"],
                        agent_id=rec["agent_id"], protocol=rec["protocol"], tool=rec["tool"])
        act.request_id = request_id  # same trace across approval boundary
        d = decide(self.engine, act)  # re-decide: policy may have tightened
        if not approved:
            self._log(act, d, "DENIED")
            raise PermissionError(f"AGENTGUARD DENIED {act.describe()} [request_id={request_id}]")
        if not d.allowed and not d.needs_approval:
            self._log(act, d, "BLOCKED")
            raise PermissionError(f"AGENTGUARD BLOCKED {act.describe()}: policy now denies it")
        self._log(act, d, "APPROVED")
        return self._run(rec["tool"], act, preapproved=True)


def default_registry(sandbox: GuardedSandbox) -> Dict[str, Callable[[AgentAction], Any]]:
    """Default tool implementations delegate to the guarded sandbox runtime."""
    def _read(a: AgentAction) -> str:
        return sandbox.read_file(a.resource)

    def _write(a: AgentAction) -> str:
        content = a.args[0] if a.args else ""
        sandbox.write_file(a.resource, content)
        return "ok"

    def _exec(a: AgentAction) -> Any:
        cmd = [a.resource, *a.args] if a.args else a.resource
        r = sandbox.run_command(cmd)
        return r.stdout

    def _net(a: AgentAction) -> str:
        sandbox.check_url(a.resource)
        return "ok"

    return {
        "filesystem.read": _read, "fs.read": _read,
        "filesystem.write": _write, "fs.write": _write,
        "shell.execute": _exec, "shell.exec": _exec, "exec": _exec,
        "http.request": _net, "http.fetch": _net, "network.request": _net,
    }
