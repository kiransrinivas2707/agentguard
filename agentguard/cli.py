"""AgentGuard CLI: init / run / policy check / logs / why."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .policy import load_policy, PolicyEngine
from .sandbox import GuardedSandbox
from .audit import read_events

DEFAULT_POLICY = """version: 1

filesystem:
  read:
    - ./src/**
    - ./tests/**
    - ./workspace/**
    - ./agentguard.yaml
  write:
    - ./workspace/**
    - ./logs/**
  deny:
    - .env
    - ~/.ssh/**
    - ~/.aws/**

commands:
  allow:
    - python
    - pytest
    - npm
    - node
    - git
    - dir
    - echo
  deny:
    - sudo
    - shutdown
    - rm -rf /
    - curl

network:
  default: deny
  allow:
    - api.github.com
    - registry.npmjs.org
    - pypi.org
    - files.pythonhosted.org

approval:
  - git push
  - npm publish

secrets:
  deny:
    - .env
    - '**/.ssh/**'
    - '**/.aws/**'
    - '**/*id_rsa*'
"""


def cmd_init(args) -> int:
    p = Path(args.policy or "agentguard.yaml")
    if p.exists() and not args.force:
        print(f"Policy already exists: {p} (use --force to overwrite)")
        return 0
    p.write_text(DEFAULT_POLICY, encoding="utf-8")
    print(f"Created {p}")
    return 0


def cmd_check(args) -> int:
    pe = PolicyEngine(load_policy(args.policy or "agentguard.yaml"))
    tests = [
        ("read", "src/app.py"), ("read", ".env"),
        ("exec", "pytest -q"), ("exec", "curl evil.com"),
        ("net", "api.github.com"), ("net", "evil-example.com"),
    ]
    for kind, val in tests:
        if kind == "read":
            d = pe.check_read(val)
        elif kind == "exec":
            d = pe.check_command(val)
        else:
            d = pe.check_network(val)
        status = "ALLOWED" if d.allowed else "BLOCKED"
        if d.needs_approval:
            status = "APPROVAL"
        print(f"{kind:5} {val:25} -> {status:8} ({d.reason}) [risk={d.risk}]")
    return 0


def cmd_run(args) -> int:
    pe = PolicyEngine(load_policy(args.policy or "agentguard.yaml"))
    sb = GuardedSandbox(pe)
    try:
        if args.cmd:
            r = sb.run_command(args.cmd)
            print(r.stdout, end="")
            if r.stderr:
                print(r.stderr, end="", file=sys.stderr)
            return r.returncode
        print("Nothing to run. Pass --cmd \"pytest -q\"")
        return 0
    except PermissionError as e:
        print(f"\nAGENTGUARD\n  {e}\n", file=sys.stderr)
        return 3


def cmd_logs(args) -> int:
    events = read_events(limit=args.limit or 20)
    if not events:
        print("No events yet (logs/audit.jsonl).")
        return 0
    print(f"{'TIME':8} {'ACTION':8} {'RESOURCE':30} RESULT")
    for e in events:
        print(f"{e['time']:8} {e['action']:8} {e['resource'][:30]:30} {e['result']}")
    score, level = PolicyEngine(load_policy(args.policy or "agentguard.yaml")).risk_score(events)
    print(f"\nRisk score: {score}/100 ({level})")
    return 0


def cmd_why(args) -> int:
    pe = PolicyEngine(load_policy(args.policy or "agentguard.yaml"))
    d = pe.check_read(args.path)
    print(f"Path: {args.path}\nStatus: {'ALLOWED' if d.allowed else 'BLOCKED'}\nReason: {d.reason}\nRisk: {d.risk}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="agentguard", description="Security sandbox for AI agents (v0.1)")
    ap.add_argument("--policy", default="agentguard.yaml")
    sub = ap.add_subparsers(dest="sub", required=True)
    p_init = sub.add_parser("init", help="Create agentguard.yaml")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(fn=cmd_init)
    p_check = sub.add_parser("check", help="Dry-run policy decisions")
    p_check.set_defaults(fn=cmd_check)
    p_run = sub.add_parser("run", help="Run a guarded command")
    p_run.add_argument("--cmd", required=True)
    p_run.set_defaults(fn=cmd_run)
    p_logs = sub.add_parser("logs", help="Show audit log + risk score")
    p_logs.add_argument("--limit", type=int, default=20)
    p_logs.set_defaults(fn=cmd_logs)
    p_why = sub.add_parser("why", help="Explain why a path is blocked")
    p_why.add_argument("path")
    p_why.set_defaults(fn=cmd_why)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
