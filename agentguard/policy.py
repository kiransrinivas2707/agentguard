"""Policy engine: YAML policy -> allow / deny / approval decisions."""
from __future__ import annotations
import fnmatch
import os
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

# Paths that are always treated as secrets (unless explicitly allowed)
DEFAULT_SECRET_PATTERNS = [
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/.ssh/**",
    "**/.aws/**",
    "**/*id_rsa*",
    "**/*id_ed25519*",
    "**/*.pem",
    "**/credentials.json",
    "**/.npmrc",
]

RISK_TABLE = {
    "read": 5,
    "write": 15,
    "exec_low": 5,      # python, pytest, node, git status
    "exec_medium": 15,  # npm install, pip install
    "exec_high": 30,    # git push, docker, deploy
    "network": 10,
    "secret": 50,
    "approval": 20,
}

APPROVAL_HINTS = ["git push", "npm publish", "pip publish", "docker push", "kubectl", "terraform apply", "rm ", "delete"]


def _norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _matches(path: str, patterns: List[str]) -> bool:
    p = _norm(path)
    name = os.path.basename(p)
    for pat in patterns:
        pat_n = _norm(pat)
        # match full path, basename, or fnmatch with ** support
        if fnmatch.fnmatch(p, pat_n) or fnmatch.fnmatch(name, pat_n) or fnmatch.fnmatch(p, "**/" + pat_n):
            return True
        # prefix rule: "./src" allows "./src/app.py"
        if p == pat_n or p.startswith(pat_n.rstrip("*").rstrip("/") + "/"):
            return True
    return False


class Decision:
    def __init__(self, allowed: bool, reason: str, risk: str = "LOW", needs_approval: bool = False):
        self.allowed = allowed
        self.reason = reason
        self.risk = risk
        self.needs_approval = needs_approval

    def to_dict(self) -> Dict:
        return {"allowed": self.allowed, "reason": self.reason, "risk": self.risk, "needs_approval": self.needs_approval}


def load_policy(path: str | Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # normalize defaults
    data.setdefault("version", 1)
    data.setdefault("filesystem", {}).setdefault("read", [])
    data.setdefault("filesystem", {}).setdefault("write", [])
    data.setdefault("filesystem", {}).setdefault("deny", [])
    data.setdefault("commands", {}).setdefault("allow", [])
    data.setdefault("commands", {}).setdefault("deny", [])
    data.setdefault("network", {}).setdefault("default", "deny")
    data.setdefault("network", {}).setdefault("allow", [])
    data.setdefault("approval", [])
    data.setdefault("secrets", {}).setdefault("deny", DEFAULT_SECRET_PATTERNS)
    return data


class PolicyEngine:
    def __init__(self, policy: Dict):
        self.policy = policy

    # ---- filesystem ----
    def check_read(self, path: str) -> Decision:
        fs = self.policy.get("filesystem", {})
        secrets = self.policy.get("secrets", {}).get("deny", DEFAULT_SECRET_PATTERNS)
        if _matches(path, secrets) or _matches(path, fs.get("deny", [])):
            return Decision(False, f"Sensitive/denied path: {path}", risk="CRITICAL")
        if _matches(path, fs.get("read", []) + fs.get("write", [])):
            return Decision(True, f"Read allowed by filesystem policy", risk="LOW")
        return Decision(False, f"Read not in allowlist: {path}", risk="MEDIUM")

    def check_write(self, path: str) -> Decision:
        fs = self.policy.get("filesystem", {})
        secrets = self.policy.get("secrets", {}).get("deny", DEFAULT_SECRET_PATTERNS)
        if _matches(path, secrets) or _matches(path, fs.get("deny", [])):
            return Decision(False, f"Sensitive/denied path: {path}", risk="CRITICAL")
        if _matches(path, fs.get("write", [])):
            return Decision(True, "Write allowed by filesystem policy", risk="LOW")
        return Decision(False, f"Write not in allowlist: {path}", risk="MEDIUM")

    # ---- commands ----
    def check_command(self, command: str) -> Decision:
        cmd = command.strip()
        base = cmd.split()[0] if cmd.split() else ""
        cmds = self.policy.get("commands", {})
        deny = cmds.get("deny", [])
        allow = cmds.get("allow", [])
        # deny wins
        for d in deny:
            if cmd == d or base == d or cmd.startswith(d):
                return Decision(False, f"Command denied: {d}", risk="HIGH")
        # approval list
        for a in list(self.policy.get("approval", [])) + APPROVAL_HINTS:
            if a and a in cmd:
                return Decision(True, f"Approval required: {a}", risk="HIGH", needs_approval=True)
        for a in allow:
            if base == a or cmd.startswith(a):
                risk = "LOW" if base in ("python", "pytest", "node", "git") and "push" not in cmd else "MEDIUM"
                return Decision(True, f"Command allowed: {base}", risk=risk)
        return Decision(False, f"Command not in allowlist: {base}", risk="MEDIUM")

    # ---- network ----
    def check_network(self, domain: str) -> Decision:
        net = self.policy.get("network", {})
        allowed = net.get("allow", [])
        d = domain.lower().strip()
        for a in allowed:
            a = str(a).lower().strip()
            if d == a or (a.startswith("*.") and d.endswith(a[1:])) or d.endswith("." + a):
                return Decision(True, f"Network allowed: {domain}", risk="MEDIUM")
        if net.get("default", "deny") == "allow":
            return Decision(True, "Network allowed by default-allow", risk="MEDIUM")
        return Decision(False, f"Network denied (default deny): {domain}", risk="HIGH")

    def risk_score(self, events: List[Dict]) -> Tuple[int, str]:
        score = 0
        for e in events:
            kind = e.get("kind", "read")
            result = e.get("result", "ALLOWED")
            if result == "BLOCKED":
                score += 5
            elif kind == "read":
                score += RISK_TABLE["read"] if "ssh" not in str(e) else RISK_TABLE["secret"]
            elif kind == "write":
                score += RISK_TABLE["write"]
            elif kind == "exec":
                score += RISK_TABLE["exec_medium"] if "install" in str(e) else RISK_TABLE["exec_low"]
            elif kind == "network":
                score += RISK_TABLE["network"]
            if e.get("needs_approval"):
                score += RISK_TABLE["approval"]
        score = min(score, 100)
        level = "LOW" if score < 30 else "MEDIUM" if score < 60 else "HIGH" if score < 85 else "CRITICAL"
        return score, level
