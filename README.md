# AgentGuard — Security Sandbox for AI Agents (v0.1)

> Reduces agent capabilities through isolation, permissions, and auditing.
> Does NOT make arbitrary agents "secure" — sandbox/runtime config still matters.

## What it is

```
AI Agent -> AgentGuard (policy + audit) -> Sandbox / OS
```

5 layers (v0.1 implements advisory enforcement on Windows, kernel-backed later on Linux):
1. Filesystem allow/deny (`agentguard.yaml`)
2. Command allow/deny + approval (`git push` -> APPROVAL)
3. Network default-deny + allowlist
4. Secrets protection (`.env`, `~/.ssh`, `~/.aws`)
5. Audit log + risk score (`logs/audit.jsonl`)

## Security Demo

AgentGuard executed 10 attack scenarios:

| Allowed | 4 |
| Blocked | 5 |
| Approval | 1 |

Risk: 65/100 HIGH (see `docs/risk.md` for math).

Hardening suite: `22 passed, 1 skipped` — traversal, prefix-confusion,
symlink, command/shell injection, network bypass (localhost, private IPs,
`169.254.169.254`), secret redaction, sandbox-escape enforcement
(`tests/test_hardening.py`). Evidence: `dashboard/test_report.html`.

## MCP boundary (v0.3)

One action model, one engine — MCP is a thin adapter (`agentguard/mcp.py`):

```
$ python -m agentguard.cli mcp

filesystem.read({'path': 'workspace/app.py'})   -> ALLOWED
filesystem.read({'path': '~/.ssh/id_rsa'})      -> BLOCKED
shell.execute({'command': 'git push origin main'}) -> APPROVAL
http.request({'url': 'https://evil-example.com/x'}) -> BLOCKED
```

Denied tools never execute (killer test: `test_mcp_killer_tool_never_executes`).

## Quickstart (Windows, Python 3.13)

```powershell
pip install -r requirements.txt
python -m agentguard.cli --policy agentguard.yaml init
python -m agentguard.cli --policy agentguard.yaml check
python -m agentguard.cli --policy agentguard.yaml run --cmd "echo hello"
python -m agentguard.cli logs --limit 20
python -m agentguard.cli why .env
pytest -q
```

Demo block:

```
$ python -m agentguard.cli why ~/.ssh/id_rsa
Path: ~/.ssh/id_rsa
Status: BLOCKED
Reason: Sensitive/denied path
Risk: CRITICAL
```

## Roadmap

- v0.1 (this): CLI + YAML policy + audit + tests ✅
- v0.2: Network proxy + DNS filtering, Docker `sbx`-style microVM run
- v0.3: Secret injection (agent uses token without seeing it)
- v0.4: Human approval workflow (Allow once / Deny)
- v0.5: MCP / LangChain / OpenAI agent adapters
- v0.6: Next.js dashboard (risk score, policy editor, live events)

## Resources researched

- Docker Sandboxes (microVM, private daemon, network proxy)
- `nono` (Landlock/Seatbelt capability shell, `nono why`)
- `agent-sandbox` (Rust fs/net/rlimit + audit trail)
- Codex CLI profiles: `read-only / workspace-write / danger-full-access`
- Rust `clap` 4.5 derive for future Rust rewrite

## Security note

Windows v0.1 is **advisory enforcement** (process-level checks).
Production isolation needs Docker + Linux (namespaces, seccomp, Landlock).
See `Dockerfile` for next step.
