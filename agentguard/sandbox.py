"""Sandbox: enforce policy before touching fs / subprocess / network."""
from __future__ import annotations
import subprocess
import urllib.parse
from pathlib import Path

from .policy import PolicyEngine
from .audit import log_event


class GuardedSandbox:
    def __init__(self, policy_engine: PolicyEngine, log_path: str | Path = "logs/audit.jsonl"):
        self.pe = policy_engine
        self.log_path = Path(log_path)

    def _log(self, action, resource, decision, kind):
        result = "ALLOWED" if decision.allowed else "BLOCKED"
        if decision.needs_approval:
            result = "APPROVAL"
        return log_event(action, resource, result, decision.reason, kind=kind,
                         risk=decision.risk, log_path=self.log_path)

    def read_file(self, path: str) -> str:
        d = self.pe.check_read(path)
        self._log("READ", path, d, "read")
        if not d.allowed:
            raise PermissionError(f"AGENTGUARD BLOCKED read {path}: {d.reason} [risk={d.risk}]")
        return Path(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        d = self.pe.check_write(path)
        self._log("WRITE", path, d, "write")
        if not d.allowed:
            raise PermissionError(f"AGENTGUARD BLOCKED write {path}: {d.reason} [risk={d.risk}]")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def run_command(self, cmd: str | list, timeout: int = 30) -> subprocess.CompletedProcess:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        d = self.pe.check_command(cmd_str)
        self._log("EXEC", cmd_str, d, "exec")
        if not d.allowed:
            raise PermissionError(f"AGENTGUARD BLOCKED exec '{cmd_str}': {d.reason}")
        if d.needs_approval:
            raise PermissionError(f"AGENTGUARD APPROVAL required for '{cmd_str}': {d.reason}")
        return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)

    def check_url(self, url: str):
        domain = urllib.parse.urlparse(url).netloc.split(":")[0] or url
        d = self.pe.check_network(domain)
        self._log("NETWORK", domain, d, "network")
        if not d.allowed:
            raise PermissionError(f"AGENTGUARD BLOCKED network {domain}: {d.reason}")
        return True
