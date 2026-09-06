"""Audit log: JSONL append-only trail + simple query."""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Dict, List

DEFAULT_LOG = Path("logs/audit.jsonl")


def log_event(action: str, resource: str, result: str, reason: str = "", kind: str = "read",
              risk: str = "LOW", log_path: str | Path = DEFAULT_LOG) -> Dict:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "time": time.strftime("%H:%M:%S"),
        "timestamp": time.time(),
        "action": action.upper(),
        "resource": resource,
        "result": result,
        "reason": reason,
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
