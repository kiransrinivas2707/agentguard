"""Real coding-agent end-to-end (v0.4): a working agent program that does its
job ONLY through the AgentGuard MCP boundary.

Run:  python examples/coding-agent/agent.py
Then: python -m agentguard.cli pending        # see queued git push
      python -m agentguard.cli approve <id>   # human approves -> executes
      python -m agentguard.cli logs --limit 20
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentguard.approval import ApprovalNeeded
from agentguard.mcp import MCPGateway
from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox

AGENT_ID = "coding-agent-v1"


def step(gw: MCPGateway, tool: str, args: dict) -> None:
    try:
        out = gw.handle(tool, args, agent_id=AGENT_ID)
        print(f"  ALLOWED  {tool} {list(args.values())[0]!s:.60}")
        if out and isinstance(out, str) and len(out) < 300:
            print(f"           -> {out.strip()[:200]}")
    except ApprovalNeeded as a:
        print(f"  APPROVAL {tool} -> queued [{a.request_id}] (run: approve {a.request_id})")
    except PermissionError as e:
        print(f"  BLOCKED  {tool} -> {str(e)[:100]}")


def main() -> int:
    pe = PolicyEngine(load_policy("agentguard.yaml"))
    gw = MCPGateway(pe, GuardedSandbox(pe))
    print(f"[agent:{AGENT_ID}] task: add greeting, test it, ship it")
    step(gw, "filesystem.read", {"path": "workspace/app.py"})
    Path("workspace").mkdir(exist_ok=True)
    step(gw, "filesystem.write", {"path": "workspace/greet.py",
                                  "content": "def greet(n):\n    return f'hi {n}'\n"})
    step(gw, "shell.execute", {"command": "pytest -q"})
    step(gw, "filesystem.read", {"path": ".env"})          # nosy agent moment
    step(gw, "shell.execute", {"command": "git push origin main"})
    print(f"[agent:{AGENT_ID}] done. decisions in logs/audit.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
