"""Agent boundary (v0.3): ONE action model, ONE engine, many adapters.

Every adapter (CLI, MCP, future agent APIs) normalizes external requests into
AgentAction and flows through PolicyEngine -> Runtime -> Audit. Adapters must
never implement their own security logic.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .policy import PolicyEngine

ACTIONS = {"READ", "WRITE", "EXEC", "NETWORK"}


@dataclass
class AgentAction:
    action: str                      # READ | WRITE | EXEC | NETWORK
    resource: str                    # path | program | host
    args: list = field(default_factory=list)
    agent_id: str = "local-agent"
    protocol: str = "cli"            # cli | mcp | api
    tool: str = ""                   # e.g. filesystem.read (mcp only)
    timestamp: float = field(default_factory=time.time)

    def describe(self) -> str:
        return f"{self.action} {self.resource} {self.args}".strip()


def normalize(action: str, resource: str, args: list | None = None,
              agent_id: str = "local-agent", protocol: str = "cli",
              tool: str = "") -> AgentAction:
    """Fail-closed normalizer (unknown action / empty resource -> ValueError)."""
    a = str(action or "").upper().strip()
    if a not in ACTIONS:
        raise ValueError(f"Unknown action {action!r} (fail-closed; want {sorted(ACTIONS)})")
    r = str(resource or "").strip()
    if not r:
        raise ValueError("Empty resource (fail-closed)")
    return AgentAction(action=a, resource=r, args=list(args or []),
                       agent_id=agent_id, protocol=protocol, tool=tool)


def decide(engine: PolicyEngine, act: AgentAction):
    """Route to the single PolicyEngine. No adapter-local policy."""
    if act.action == "READ":
        return engine.check_read(act.resource)
    if act.action == "WRITE":
        return engine.check_write(act.resource)
    if act.action == "NETWORK":
        return engine.check_network(act.resource)
    cmd = [act.resource, *act.args] if act.args else act.resource
    return engine.check_command(cmd)


def execute(engine: PolicyEngine, act: AgentAction, tool_impl: Callable[[AgentAction], Any],
            log_fn: Callable[..., Any] | None = None) -> Any:
    """Enforce then run. tool_impl is NEVER called on DENY/APPROVAL (killer invariant)."""
    d = decide(engine, act)
    result = "ALLOWED" if d.allowed else "BLOCKED"
    if d.needs_approval:
        result = "APPROVAL"
    if log_fn:
        log_fn(act, d, result)
    if not d.allowed:
        raise PermissionError(f"AGENTGUARD BLOCKED {act.describe()}: {d.reason}")
    if d.needs_approval:
        raise PermissionError(f"AGENTGUARD APPROVAL required for {act.describe()}: {d.reason}")
    return tool_impl(act)
