"""MCP adapter (v0.3): thin mapping from MCP tool calls to AgentAction.

The adapter NEVER decides security itself. It normalizes, then the single
PolicyEngine decides, then the runtime runs. On DENY/APPROVAL the underlying
tool implementation is never invoked (killer invariant).
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict

from .actions import AgentAction, execute, normalize
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
                 registry: Dict[str, Callable[[AgentAction], Any]] | None = None):
        self.engine = engine
        self.sandbox = sandbox
        self.registry = registry or default_registry(sandbox)

    def handle(self, tool: str, arguments: Dict[str, Any], agent_id: str = "mcp-agent") -> Any:
        act = to_action(tool, arguments, agent_id)

        def _log(a: AgentAction, d, result: str) -> None:
            from .audit import redact_resource
            log_event(a.action, redact_resource(a.resource), result, d.reason,
                      kind=a.action.lower(), risk=d.risk, log_path=self.sandbox.log_path,
                      agent_id=a.agent_id, protocol=a.protocol, tool=a.tool)

        def _run(a: AgentAction) -> Any:
            impl = self.registry.get(tool)
            if impl is None:
                raise ValueError(f"No implementation for tool {tool!r} (fail-closed)")
            return impl(a)

        return execute(self.engine, act, _run, log_fn=_log)


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
