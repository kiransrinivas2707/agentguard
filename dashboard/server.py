"""AgentGuard dashboard server (Flask). Serves UI + JSON APIs from audit log."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, jsonify, send_from_directory, request
import yaml

from agentguard.policy import load_policy, PolicyEngine
from agentguard.audit import read_events

app = Flask(__name__)
BASE = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = BASE / "dashboard"
POLICY_PATH = BASE / "agentguard.yaml"
LOG_PATH = BASE / "logs" / "audit.jsonl"

@app.get("/")
def index():
    return send_from_directory(str(DASHBOARD_DIR), "index.html")

@app.get("/api/policy")
def api_policy():
    return jsonify(load_policy(POLICY_PATH))

@app.get("/api/events")
def api_events():
    limit = int(request.args.get("limit", 200))
    return jsonify(read_events(LOG_PATH, limit=limit))

@app.get("/api/summary")
def api_summary():
    events = read_events(LOG_PATH, limit=500)
    pe = PolicyEngine(load_policy(POLICY_PATH))
    score, level = pe.risk_score(events)
    allowed = sum(1 for e in events if e["result"] == "ALLOWED")
    blocked = sum(1 for e in events if e["result"] == "BLOCKED")
    approval = sum(1 for e in events if e["result"] == "APPROVAL")
    by_action: dict[str, int] = {}
    for e in events:
        by_action[e["action"]] = by_action.get(e["action"], 0) + 1
    return jsonify({
        "total": len(events), "allowed": allowed, "blocked": blocked,
        "approval": approval, "risk_score": score, "risk_level": level,
        "by_action": by_action,
    })

@app.post("/api/run-demo")
def api_run_demo():
    from dashboard.demo import run_demo
    results = run_demo(str(LOG_PATH))
    return jsonify([{"scenario": n, "verdict": v} for n, v in results])

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
