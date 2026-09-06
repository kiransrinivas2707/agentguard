# SECURITY.md (skills §29-30)

## What AgentGuard protects (v0.2, Python ref impl + Docker image)
- Policy-based allow/deny/approval for file read/write, commands, network domain/IP.
- Secret-path redaction: `.env`, `~/.ssh`, `~/.aws`, keys never persist raw in `logs/audit.jsonl`; errors say `sensitive-resource`.
- Fail-closed policy validation: unknown fields, wrong types raise instead of granting.
- Traversal/prefix safety: `..` collapsed, `workspace-evil` does not inherit `workspace/`, absolute escapes denied.
- Command injection: shell metacharacters (`; && || | \` $()`) denied in string form; absolute-path programs matched by basename (`/usr/bin/curl` = `curl`).
- Network bypass: IP literals only if explicitly listed; `127.0.0.1`, `localhost`, RFC1918, `169.254.169.254` denied by default.

## What it does NOT protect (no false claims)
- Windows v0.2 is advisory enforcement (process-level checks). A malicious in-process caller can bypass checks by not calling them.
- No kernel sandbox yet: needs Docker/Linux namespaces, seccomp, Landlock (see skills §3) for real isolation.
- No resource limits, no TOCTOU-safe file open, no DNS-redirect or TLS inspection, no multi-user auth.
- Do not use as sole boundary for untrusted code on a sensitive host.

## Reporting
Test locally first (`pytest -q`). Do not post live secrets or exploit details publicly; share redacted logs.
