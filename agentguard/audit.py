"""Audit log: JSONL append-only trail + simple query (skills §10/§11)."""
from __future__ import annotations
import fnmatch
import json
import os
import time
from pathlib import Path
from typing import Dict, List

DEFAULT_LOG = Path("logs/audit.jsonl")

_SECRET_HINTS = (".env", ".ssh", ".aws", "id_rsa", "id_ed25519", ".pem", "credentials.json", ".npmrc")


def redact_resource(resource: str) -> str:
    r = str(resource).replace("\\", "/")
    low = r.lower()
    if any(h in low for h in _SECRET_HINTS):
        return "[REDACTED]"
    return str(resource)


def log_event(action: str, resource: str, result: str, reason: str = "", kind: str = "read",
              risk: str = "LOW", log_path: str | Path = DEFAULT_LOG, agent_id: str = "local-agent") -> Dict:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    safe_resource = redact_resource(resource)
    # Never persist secret values even if they slip into reason text
    safe_reason = str(reason)
    for h in _SECRET_HINTS:
        if h in safe_reason.lower() and "sensitive-resource" not in safe_reason.lower():
            safe_reason = "sensitive-resource (redacted)"
            break
    event = {
        "time": time.strftime("%H:%M:%S"),
        "timestamp": time.time(),
        "agent_id": agent_id,
        "action": action.upper(),
        "resource": safe_resource,
        "result": result,
        "decision": result,
        "reason": safe_reason,
        "kind": kind,
        "risk": risk,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return event


def read_events(log_path: str | Path = DEFAULT_LOG, limit: int = 50) -> List[Dict]:
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(x) for x in lines if x.strip()]
    return events[-limit:]
