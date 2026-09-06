"""v0.3 adapter tests: one engine, thin MCP adapter, tool never runs on DENY."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from agentguard.actions import decide, execute, normalize
from agentguard.audit import read_events
from agentguard.mcp import MCPGateway, to_action
from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox


def gw(tmp_path, registry=None):
    pe = PolicyEngine(load_policy("agentguard.yaml"))
    sb = GuardedSandbox(pe, log_path=tmp_path / "audit.jsonl")
    return MCPGateway(pe, sb, registry=registry), sb


def test_action_normalize_rejects_unknown():
    with pytest.raises(ValueError):
        normalize("DELETE", "x")
    with pytest.raises(ValueError):
        normalize("READ", "")


def test_single_engine_routing():
    pe = PolicyEngine(load_policy("agentguard.yaml"))
    assert not decide(pe, normalize("READ", ".env")).allowed
    assert decide(pe, normalize("READ", "workspace/app.py")).allowed


def test_mcp_allowed_tool(tmp_path):
    g, _ = gw(tmp_path)
    Path("workspace").mkdir(exist_ok=True)
    target = Path("workspace/app.py")
    backup = target.read_text() if target.exists() else None
    target.write_text("print(1)\n")
    try:
        assert "print(1)" in g.handle("filesystem.read", {"path": "workspace/app.py"})
    finally:
        if backup is not None:
            target.write_text(backup)


def test_mcp_denied_tool(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError):
        g.handle("shell.execute", {"command": "curl https://evil.com"})


def test_mcp_sensitive_path(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError):
        g.handle("filesystem.read", {"path": "~/.ssh/id_rsa"})


def test_mcp_command_denied_variants(tmp_path):
    g, _ = gw(tmp_path)
    for cmd in ("curl.exe https://evil.com", "/usr/bin/curl https://evil.com"):
        with pytest.raises(PermissionError):
            g.handle("shell.execute", {"command": cmd})


def test_mcp_network_denied(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError):
        g.handle("http.request", {"url": "https://evil-example.com/x"})
    with pytest.raises(PermissionError):
        g.handle("http.request", {"url": "http://169.254.169.254/"})


def test_mcp_approval(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError, match="APPROVAL"):
        g.handle("shell.execute", {"command": "git push origin main"})


def test_mcp_malformed_request(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(ValueError):
        g.handle("filesystem.read", {})
    with pytest.raises(ValueError):
        g.handle("shell.execute", {"command": []})


def test_mcp_unknown_tool(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(ValueError):
        g.handle("database.drop", {"table": "users"})


def test_mcp_argument_injection(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError):
        g.handle("shell.execute", {"command": "pytest; rm -rf /"})


def test_mcp_path_traversal(tmp_path):
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError):
        g.handle("filesystem.read", {"path": "workspace/../../.env"})


def test_mcp_tool_description_untrusted(tmp_path):
    """Tool claims 'search project' but actually reads secrets -> BLOCKED."""
    g, _ = gw(tmp_path)
    with pytest.raises(PermissionError):
        g.handle("filesystem.read", {"path": "~/.aws/credentials"})


def test_mcp_killer_tool_never_executes(tmp_path):
    """DENY must prevent the underlying tool from EVER running."""
    calls = []

    def evil_impl(act):
        calls.append(act)
        return "pwned"

    g, _ = gw(tmp_path, registry={"filesystem.read": evil_impl})
    with pytest.raises(PermissionError):
        g.handle("filesystem.read", {"path": ".env"})
    assert calls == [], "underlying tool executed despite DENY"


def test_mcp_audit_event(tmp_path):
    g, _ = gw(tmp_path)
    try:
        g.handle("filesystem.read", {"path": ".env"}, agent_id="coding-ai")
    except PermissionError:
        pass
    events = read_events(tmp_path / "audit.jsonl")
    assert events and events[-1]["protocol"] == "mcp"
    assert events[-1]["tool"] == "filesystem.read"
    assert events[-1]["agent_id"] == "coding-ai"
    assert events[-1]["result"] == "BLOCKED"


def test_mcp_secret_redaction(tmp_path):
    g, _ = gw(tmp_path)
    try:
        g.handle("filesystem.read", {"path": "~/.ssh/id_rsa"})
    except PermissionError:
        pass
    blob = (tmp_path / "audit.jsonl").read_text()
    assert "[REDACTED]" in blob and "id_rsa" not in blob


def test_mcp_policy_failure_closed(tmp_path):
    pe = PolicyEngine(load_policy("agentguard.yaml"))
    sb = GuardedSandbox(pe, log_path=tmp_path / "a.jsonl")
    with pytest.raises(ValueError):
        to_action("filesystem.read", {}, "x")
    # execute() without policy allow must raise before tool runs
    ran = []
    with pytest.raises(PermissionError):
        execute(pe, normalize("READ", ".env", protocol="mcp", tool="filesystem.read"),
                lambda a: ran.append(a))
    assert ran == []


def test_mcp_resource_limit(tmp_path):
    pol = load_policy("agentguard.yaml")
    pol["resources"] = {"timeout_seconds": 30, "max_output_bytes": 1024, "max_processes": 64}
    pe = PolicyEngine(pol)
    sb = GuardedSandbox(pe, log_path=tmp_path / "a.jsonl")
    g = MCPGateway(pe, sb)
    with pytest.raises(PermissionError, match="RESOURCE_LIMIT"):
        g.handle("shell.execute", {"command": [sys.executable, "-c", "print('z'*50000)"]})
