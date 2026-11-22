"""Human approval (v0.4): APPROVAL becomes a real security gate.

Agent -> gateway queues request -> human APPROVE/DENY -> only approved actions
execute. Every step carries the same request_id so one operation traces across
request -> decision -> approval -> execution -> audit.
"""
from __future__ import annotations
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    resource: str
    args: list = field(default_factory=list)
    agent_id: str = ""
    protocol: str = ""
    tool: str = ""
    reason: str = ""
    status: str = "pending"   # pending | approved | denied
    created: float = field(default_factory=time.time)
    decided: float = 0.0
    decided_by: str = ""


class ApprovalNeeded(PermissionError):
    def __init__(self, request_id: str, describe: str):
        super().__init__(f"AGENTGUARD APPROVAL required for {describe} [request_id={request_id}]")
        self.request_id = request_id


class ApprovalStore:
    def __init__(self, path: str | Path = "logs/approvals.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list:
        try:
            return json.loads(self.path.read_text(encoding="utf-8") or "[]")
        except Exception:
            return []

    def _write(self, items: list) -> None:
        self.path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def request(self, act, reason: str) -> ApprovalRequest:
        items = self._read()
        if any(i["request_id"] == act.request_id for i in items):
            raise ValueError(f"Duplicate request_id {act.request_id} (fail-closed)")
        req = ApprovalRequest(request_id=act.request_id, action=act.action,
                              resource=act.resource, args=list(act.args),
                              agent_id=act.agent_id, protocol=act.protocol,
                              tool=act.tool, reason=reason)
        items.append(asdict(req))
        self._write(items)
        return req

    def decide(self, request_id: str, approved: bool, by: str = "human") -> dict:
        items = self._read()
        for i in items:
            if i["request_id"] == request_id:
                if i["status"] != "pending":
                    raise ValueError(f"Request {request_id} already {i['status']} (fail-closed)")
                i["status"] = "approved" if approved else "denied"
                i["decided"] = time.time()
                i["decided_by"] = by
                self._write(items)
                return i
        raise KeyError(f"Unknown request_id {request_id} (fail-closed)")

    def get(self, request_id: str) -> dict | None:
        return next((i for i in self._read() if i["request_id"] == request_id), None)

    def pending(self) -> list:
        return [i for i in self._read() if i["status"] == "pending"]
