"""Policy engine: YAML policy -> allow / deny / approval decisions.

Skills.md contract: default-deny, deny-wins, fail-closed validation,
canonicalized path checks, secret redaction, shell-injection and
network-bypass resistance.
"""
from __future__ import annotations
import fnmatch
import ipaddress
import os
import shlex
from pathlib import Path, PurePosixPath
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
    "read": 5,          # allowed READ event
    "write": 15,        # allowed WRITE event
    "exec_low": 5,      # allowed low-risk exec (python, pytest, node, git status)
    "exec_medium": 15,  # allowed exec with side effects (npm/pip install)
    "network": 10,      # allowed NETWORK event
    "blocked": 5,       # any BLOCKED attempt adds this base weight
    "secret_bonus": 15,  # extra weight when BLOCKED attempt was CRITICAL/secret
    "approval": 20,     # extra weight when event needs human approval
}
# Documented risk math (P5): score = Σ per-event weights, capped at 100.
#   ALLOWED read +5 | write +15 | exec low +5 / install +15 | network +10
#   BLOCKED any +5, plus +15 more if CRITICAL secret attempt (=20)
#   APPROVAL flag +20. Bands: 0-29 LOW, 30-59 MEDIUM, 60-84 HIGH, 85-100 CRITICAL.

APPROVAL_HINTS = ["git push", "npm publish", "pip publish", "docker push", "kubectl", "terraform apply", "rm ", "delete"]

ALLOWED_TOP_FIELDS = {"version", "filesystem", "commands", "network", "approval", "secrets", "resources"}
SHELL_METACHARS = {";", "&", "|", "$", "`", "\n", "<", ">", "$(", "${"}

# Hosts that must never be reachable unless explicitly allowlisted (skills §9)
SENSITIVE_HOSTS = {"localhost", "metadata.google.internal", "metadata.google.com"}


def is_sensitive_path(p: str) -> bool:
    return _matches(p, DEFAULT_SECRET_PATTERNS)


def redact(p: str) -> str:
    """Never put raw secret paths into logs/errors (skills §10)."""
    return "[REDACTED]" if is_sensitive_path(p) else p


def _norm(p: str) -> str:
    s = p.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def _canonical(p: str) -> str:
    """Collapse .., expand ~, resolve symlinks where possible (skills §7)."""
    try:
        q = Path(p).expanduser()
        if not q.is_absolute():
            q = Path.cwd() / q
        try:
            q = q.resolve(strict=False)
        except Exception:
            pass
        s = q.as_posix()
        # also collapse any remaining .. lexically
        return os.path.normpath(s).replace("\\", "/")
    except Exception:
        return _norm(p)


def _relative_posix(canon: str) -> str:
    try:
        return Path(canon).relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        return canon


def _matches(path: str, patterns: List[str]) -> bool:
    # Skills §7: never decide on raw ".." strings. Collapse first; if the
    # path escapes via traversal, only the canonical form may grant access.
    raw_norm = _norm(path)
    has_dotdot = ".." in PurePosixPath(raw_norm).parts
    canon = _norm(_canonical(path))
    rel = _norm(_relative_posix(_canonical(path)))
    if has_dotdot:
        candidates = {canon, rel}
    else:
        candidates = {raw_norm, canon, rel, path.replace("\\", "/")}
    name = os.path.basename(raw_norm)
    for pat in patterns:
        pat_n = _norm(pat)
        for p in candidates:
            if fnmatch.fnmatch(p, pat_n) or fnmatch.fnmatch(name, pat_n) or fnmatch.fnmatch(p, "**/" + pat_n):
                return True
            # prefix rule with boundary: "./workspace" allows "./workspace/a"
            # but NOT "./workspace-evil/a" (skills §7 bad-pattern fix)
            root = pat_n.rstrip("*").rstrip("/")
            if not root or root in (".", "/"):
                continue
            if p == root or p.startswith(root + "/"):
                return True
            # also match relative form against pattern root
            rel = _norm(_relative_posix(_canonical(path)))
            if rel == root or rel.startswith(root + "/"):
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
    # Fail closed: reject unknown top-level fields (skills §6)
    unknown = set(data.keys()) - ALLOWED_TOP_FIELDS
    if unknown:
        raise ValueError(f"Invalid policy: unknown fields {sorted(unknown)} (fail-closed, see skills §6)")
    if not isinstance(data.get("version", 1), int):
        raise ValueError("Invalid policy: version must be int")
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
    # type validation (fail closed, never silently ignore)
    for section in ("read", "write", "deny"):
        v = data["filesystem"].get(section, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"Invalid policy: filesystem.{section} must be list[str]")
    for section in ("allow", "deny"):
        v = data["commands"].get(section, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"Invalid policy: commands.{section} must be list[str]")
    if data["network"].get("default") not in ("deny", "allow"):
        raise ValueError("Invalid policy: network.default must be 'deny' or 'allow'")
    if not isinstance(data.get("approval", []), list):
        raise ValueError("Invalid policy: approval must be list[str]")
    if "resources" in data:
        from .resources import ResourceLimits
        r = data["resources"]
        if not isinstance(r, dict):
            raise ValueError("Invalid policy: resources must be a mapping")
        ResourceLimits(
            timeout_seconds=int(r.get("timeout_seconds", 60)),
            max_output_bytes=int(r.get("max_output_bytes", 10 * 1024 * 1024)),
            max_memory_mb=r.get("max_memory_mb", None),
            max_processes=int(r.get("max_processes", 64)),
        ).validate()
    return data


class PolicyEngine:
    def __init__(self, policy: Dict):
        self.policy = policy

    # ---- filesystem ----
    def check_read(self, path: str) -> Decision:
        fs = self.policy.get("filesystem", {})
        secrets = self.policy.get("secrets", {}).get("deny", DEFAULT_SECRET_PATTERNS)
        if _matches(path, secrets) or _matches(path, fs.get("deny", [])):
            return Decision(False, "sensitive-resource (policy.secrets/filesystem.deny)", risk="CRITICAL")
        if _matches(path, fs.get("read", []) + fs.get("write", [])):
            return Decision(True, f"Read allowed by filesystem policy", risk="LOW")
        return Decision(False, f"Read not in allowlist: {redact(path)}", risk="MEDIUM")

    def check_write(self, path: str) -> Decision:
        fs = self.policy.get("filesystem", {})
        secrets = self.policy.get("secrets", {}).get("deny", DEFAULT_SECRET_PATTERNS)
        if _matches(path, secrets) or _matches(path, fs.get("deny", [])):
            return Decision(False, "sensitive-resource (policy.secrets/filesystem.deny)", risk="CRITICAL")
        if _matches(path, fs.get("write", [])):
            return Decision(True, "Write allowed by filesystem policy", risk="LOW")
        return Decision(False, f"Write not in allowlist: {redact(path)}", risk="MEDIUM")

    # ---- commands (skills §8: structured program + args, exact program match) ----
    @staticmethod
    def _prog_norm(name: str) -> str:
        b = os.path.basename(str(name).strip().split()[0] if str(name).strip() else "")
        b = b.lower()
        for ext in (".exe", ".bat", ".cmd", ".com", ".ps1"):
            if b.endswith(ext):
                b = b[: -len(ext)]
        return b

    @staticmethod
    def _split(cmd: str | list) -> Tuple[str, List[str], str]:
        if isinstance(cmd, list):
            parts = [str(x) for x in cmd]
            base = PolicyEngine._prog_norm(parts[0]) if parts else ""
            return base, parts[1:], " ".join(parts)
        s = str(cmd).strip()
        try:
            parts = shlex.split(s, posix=True)
        except Exception:
            parts = s.split()
        raw_base = parts[0] if parts else ""
        base = PolicyEngine._prog_norm(raw_base)
        return base, parts[1:], s

    def check_command(self, command: str | list) -> Decision:
        base, args, cmd_str = self._split(command)
        cmds = self.policy.get("commands", {})
        deny = cmds.get("deny", [])
        allow = cmds.get("allow", [])
        # fail closed on shell metachars in string form (skills §8/§18)
        if isinstance(command, str):
            for m in (";", "&&", "||", "|", "`", "$(", "${", "\n", "\r"):
                if m in cmd_str:
                    return Decision(False, f"Command denied: shell metacharacter {m!r} (use structured args)", risk="HIGH")
        # deny wins; exact program match so mycurl/curl-malicious != curl,
        # but curl.exe and /usr/bin/curl == curl (P1).
        for d in deny:
            d_parts = str(d).strip().split()
            d_prog = self._prog_norm(d_parts[0] if d_parts else "")
            d_args = d_parts[1:]
            if base == d_prog:
                if not d_args or args[: len(d_args)] == d_args or cmd_str.startswith(str(d)):
                    return Decision(False, f"Command denied: {d}", risk="HIGH")
        # approval list (substring on full command is intentional: git push vs git status)
        for a in list(self.policy.get("approval", [])) + APPROVAL_HINTS:
            if a and a in cmd_str:
                return Decision(True, f"Approval required: {a}", risk="HIGH", needs_approval=True)
        # allow: EXACT program match only (P1). git-upload-pack != git,
        # mycurl != curl. Subcommand control lives in approval/deny, not prefix.
        for a in allow:
            if base == self._prog_norm(a):
                risk = "LOW" if base in ("python", "pytest", "node", "git") and "push" not in cmd_str else "MEDIUM"
                return Decision(True, f"Command allowed: {base}", risk=risk)
        return Decision(False, f"Command not in allowlist: {base}", risk="MEDIUM")

    # ---- network (skills §9: metadata, localhost, IP literals, privates) ----
    @staticmethod
    def _host_of(value: str) -> str:
        v = value.strip()
        if "://" in v:
            from urllib.parse import urlparse
            h = urlparse(v).hostname or v
        else:
            h = v.split("/")[0].split(":")[0]
        return h.strip().strip("[]").lower()

    def check_network(self, domain: str) -> Decision:
        from urllib.parse import urlparse
        net = self.policy.get("network", {})
        allowed = [str(a).lower().strip() for a in net.get("allow", [])]
        raw = domain.strip()
        host = self._host_of(raw)
        # IP literal handling: only pass if explicitly allowlisted
        try:
            ip = ipaddress.ip_address(host)
            if str(ip) in allowed or host in allowed:
                return Decision(True, f"Network allowed: {host}", risk="MEDIUM")
            reason = "sensitive-network-range" if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved) else "default deny"
            if str(ip) == "169.254.169.254":
                reason = "cloud-metadata-endpoint"
            return Decision(False, f"Network denied ({reason}): {host}", risk="HIGH")
        except ValueError:
            pass
        if host in SENSITIVE_HOSTS and host not in allowed:
            return Decision(False, f"Network denied (sensitive-host): {host}", risk="HIGH")
        for a in allowed:
            if host == a or (a.startswith("*.") and host.endswith(a[1:])) or host.endswith("." + a):
                return Decision(True, f"Network allowed: {host}", risk="MEDIUM")
        if net.get("default", "deny") == "allow":
            return Decision(True, "Network allowed by default-allow", risk="MEDIUM")
        return Decision(False, f"Network denied (default deny): {host}", risk="HIGH")

    def risk_score(self, events: List[Dict]) -> Tuple[int, str]:
        score = 0
        for e in events:
            kind = e.get("kind", "read")
            result = e.get("result", "ALLOWED")
            if result == "BLOCKED":
                score += RISK_TABLE["blocked"]
                if e.get("risk") == "CRITICAL":
                    score += RISK_TABLE["secret_bonus"]
            elif kind == "read":
                score += RISK_TABLE["read"]
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
