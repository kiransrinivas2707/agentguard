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
