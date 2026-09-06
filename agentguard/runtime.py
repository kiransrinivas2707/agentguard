"""Runtime layer (P8): Linux kernel detection + Docker anti-escape validation.

Principle: policy decides what SHOULD happen; kernel/runtime enforces what CAN
happen. Order of investigation: namespaces -> capabilities -> seccomp ->
Landlock -> cgroups. This ref impl detects availability and validates Docker
configs; strict enforcement lands with the Linux runtime.
"""
from __future__ import annotations
import platform
from pathlib import Path


def linux_features() -> dict:
    """Detect Linux isolation primitives. Always returns names + status."""
    feats = {
        "namespaces": False, "capabilities": False, "seccomp": False,
        "landlock": False, "cgroups": False,
    }
    reasons = {}
    if platform.system() != "Linux":
        return {"os": platform.system(), "features": feats,
                "reason": "non-Linux host: kernel enforcement unavailable (advisory mode)"}
    if Path("/proc/self/ns").exists():
        feats["namespaces"] = True
    try:
        st = Path("/proc/self/status").read_text()
        for line in st.splitlines():
            if line.startswith("Seccomp:"):
                feats["seccomp"] = line.split(":")[1].strip() not in ("0", "")
            if line.startswith("CapBnd:"):
                feats["capabilities"] = True
    except Exception as e:
        reasons["status"] = str(e)
    if Path("/sys/fs/cgroup").exists():
        feats["cgroups"] = True
    if Path("/sys/kernel/security/landlock").exists():
        feats["landlock"] = True
    return {"os": "Linux", "features": feats, "reason": reasons or "probed /proc + /sys"}


DANGEROUS_MOUNTS = ("/var/run/docker.sock", "/proc", "/sys", "/dev", "/:/host", "/host")
DANGEROUS_CAPS = {"SYS_ADMIN", "ALL", "SYS_PTRACE", "NET_ADMIN"}


def validate_docker_run(cfg: dict) -> tuple[bool, list[str]]:
    """Fail-closed validator for container configs (P3/P8 escape tests).

    Rejects privileged, host network/pid, sensitive mounts, excessive caps.
    Returns (ok, reasons). Empty reasons when ok.
    """
    bad: list[str] = []
    if cfg.get("privileged"):
        bad.append("privileged=true")
    if cfg.get("network_mode") == "host" or cfg.get("network") == "host":
        bad.append("host network")
    if cfg.get("pid_mode") == "host" or cfg.get("pid") == "host":
        bad.append("host pid")
    for vol in list(cfg.get("volumes", [])) + list(cfg.get("mounts", [])):
        v = str(vol)
        for dm in DANGEROUS_MOUNTS:
            if dm in v:
                bad.append(f"dangerous mount: {v}")
                break
    for cap in list(cfg.get("cap_add", [])) + list(cfg.get("capabilities", [])):
        if str(cap).upper() in DANGEROUS_CAPS:
            bad.append(f"dangerous cap: {cap}")
    return (not bad, bad)
