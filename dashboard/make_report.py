"""Build single-file test report: dashboard/test_report.html (pytest + demo + charts)."""
from __future__ import annotations
import base64
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode() if path.exists() else ""


def main():
    # 1. fresh demo data
    from dashboard.demo import run_demo
    demo = run_demo(str(BASE / "logs" / "audit.jsonl"))
    # 2. pytest
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(BASE),
                          capture_output=True, text=True)
    # 3. summary via API (no server needed)
    from dashboard.server import app
    c = app.test_client()
    summary = c.get("/api/summary").get_json()
    events = c.get("/api/events?limit=60").get_json()
    policy = c.get("/api/policy").get_json()
    # 4. charts
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar(["Allowed", "Blocked", "Approval"],
           [summary["allowed"], summary["blocked"], summary["approval"]],
           color=["#4ade80", "#f87171", "#facc15"])
    ax.set_title(f"Demo: {summary['total']} events, risk {summary['risk_score']}/100 {summary['risk_level']}")
    plt.tight_layout()
    chart1 = BASE / "dashboard" / "report_chart.png"
    plt.savefig(chart1, dpi=120)
    plt.close()
    rows = "\n".join(
        f"<tr><td>{e.get('time')}</td><td>{e.get('action')}</td><td>{e.get('resource')}</td>"
        f"<td>{e.get('result')}</td><td>{e.get('reason')}</td></tr>" for e in events[-25:][::-1])
    demo_rows = "\n".join(f"<tr><td>{n}</td><td>{v}</td></tr>" for n, v in demo)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>AgentGuard Test Report</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e2e8f0;max-width:1000px;margin:auto;padding:24px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid #334155;padding:6px 8px;text-align:left}}
img{{max-width:100%;border-radius:10px}}pre{{background:#020617;padding:12px;border-radius:10px;overflow:auto;font-size:12px}}</style>
</head><body>
<h1>🛡️ AgentGuard Test Report (skills.md hardening)</h1>
<p>Demo + pytest + dashboard API evidence in one file. Open anytime.</p>
<h2>1. Screenshots / charts</h2>
<h3>Attack simulation result</h3>
<img src="data:image/png;base64,{b64(chart1)}">
<h3>Previous chart (test_results.png)</h3>
<img src="data:image/png;base64,{b64(BASE / 'dashboard' / 'test_results.png')}">
<h2>2. pytest</h2><pre>{(proc.stdout + proc.stderr)[-3000:]}</pre>
<h2>3. Demo scenarios (10)</h2><table><tr><th>Scenario</th><th>Verdict</th></tr>{demo_rows}</table>
<h2>4. Summary JSON</h2><pre>{json.dumps(summary, indent=2)}</pre>
<h2>5. Recent audit events</h2><table><tr><th>Time</th><th>Action</th><th>Resource</th><th>Result</th><th>Reason</th></tr>{rows}</table>
<h2>6. Policy</h2><pre>{json.dumps(policy, indent=2)[:4000]}</pre>
<h2>7. Skills.md gaps closed</h2><pre>path canonicalization + traversal/prefix-boundary (§7)
policy validation fail-closed (§6) / secret redaction §10 / structured audit §11
shell-metachar + basename matching (§8) / metadata-localhost-private IP deny (§9)
security tests: traversal, injection, bypass, redaction (§15-18) / SECURITY.md (§29-30)</pre>
<h2>8. How data flows</h2><pre>demo.py -> GuardedSandbox -> PolicyEngine + agentguard.yaml
-> logs/audit.jsonl (redacted) -> Flask /api/* -> dashboard + this report</pre>
</body></html>"""
    out = BASE / "dashboard" / "test_report.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
