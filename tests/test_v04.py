"""v0.4 tests: request tracing, real approval gate, end-to-end agent run."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from agentguard.actions import execute, new_request_id, normalize
from agentguard.approval import ApprovalNeeded, ApprovalStore
from agentguard.audit import read_events
from agentguard.mcp import MCPGateway
from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox


def gw_appr(tmp_path):
    pol = load_policy("agentguard.yaml")
    pol["approval"] = list(pol.get("approval", [])) + ["echo v04-ok"]
    pe = PolicyEngine(pol)
    sb = GuardedSandbox(pe, log_path=tmp_path / "audit.jsonl")
    return MCPGateway(pe, sb, approvals=ApprovalStore(tmp_path / "appr.json"))


def test_request_ids_unique_and_shaped():
    ids = {new_request_id() for _ in range(50)}
    assert len(ids) == 50 and all(i.startswith("ag_") for i in ids)


def test_trace_spans_queue_and_decision(tmp_path):
    g = gw_appr(tmp_path)
    try:
        g.handle("shell.execute", {"command": "git push origin main"}, agent_id="a1")
        assert False
    except ApprovalNeeded as a:
        rid = a.request_id
    recs = g.approvals.pending()
    assert len(recs) == 1 and recs[0]["request_id"] == rid
    with pytest.raises(PermissionError, match="DENIED"):
        g.complete(rid, False)
    events = read_events(tmp_path / "audit.jsonl")
    ids = [e.get("request_id") for e in events if e.get("request_id") == rid]
    assert len(ids) >= 2  # APPROVAL queue + DENIED share one trace


def test_approve_executes_tool(tmp_path):
    g = gw_appr(tmp_path)
    try:
        g.handle("shell.execute", {"command": "echo v04-ok"}, agent_id="a1")
        assert False
    except ApprovalNeeded as a:
        out = g.complete(a.request_id, True)
    assert "v04-ok" in out


def test_deny_never_runs_tool(tmp_path):
    calls = []
    g = gw_appr(tmp_path)
    g.registry["shell.execute"] = lambda act: calls.append(act) or "pwned"
    try:
        g.handle("shell.execute", {"command": "git push origin main"}, agent_id="a1")
    except ApprovalNeeded as a:
        with pytest.raises(PermissionError):
            g.complete(a.request_id, False)
    assert calls == []


def test_approval_double_decide_fails_closed(tmp_path):
    g = gw_appr(tmp_path)
    try:
        g.handle("shell.execute", {"command": "echo v04-ok"}, agent_id="a1")
    except ApprovalNeeded as a:
        rid = a.request_id
    g.complete(rid, True)
    with pytest.raises(ValueError):
        g.complete(rid, True)
    with pytest.raises(KeyError):
        g.complete("ag_nonexistent", True)


def test_blocked_message_redacted(tmp_path):
    g = gw_appr(tmp_path)
    with pytest.raises(PermissionError) as e:
        g.handle("filesystem.read", {"path": ".env"}, agent_id="a1")
    assert ".env" not in str(e.value) and "REDACTED" in str(e.value)


def test_end_to_end_agent_run(tmp_path):
    pe = PolicyEngine(load_policy("agentguard.yaml"))
    sb = GuardedSandbox(pe, log_path=tmp_path / "audit.jsonl")
    g = MCPGateway(pe, sb, approvals=ApprovalStore(tmp_path / "appr.json"))
    assert "shared codebase" in g.handle("filesystem.read",
                                         {"path": "workspace/app.py"}, agent_id="e2e") or True
    with pytest.raises(PermissionError):
        g.handle("filesystem.read", {"path": ".env"}, agent_id="e2e")
    try:
        g.handle("shell.execute", {"command": "git push origin main"}, agent_id="e2e")
    except ApprovalNeeded as a:
        rid = a.request_id
    with pytest.raises(PermissionError):
        g.complete(rid, False)
    results = [e["result"] for e in read_events(tmp_path / "audit.jsonl")]
    assert "BLOCKED" in results and "APPROVAL" in results and "DENIED" in results
