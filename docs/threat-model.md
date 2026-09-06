# Threat model (skills §14, P3/P6)

Assets: host filesystem, credentials, network, source code, cloud/prod systems.
Attacker: buggy/compromised agent, prompt injection, malicious repo or dependency.
Attacks covered by `tests/test_hardening.py`: filesystem escape, traversal,
prefix-confusion (`/workspace` vs `/workspace-evil`), symlink escape, command/
shell injection, network bypass (localhost, private IPs, `169.254.169.254`,
IP literals), secret exfiltration via logs, sandbox-escape paths
(`/etc/passwd`, `/proc`, `/sys`, `/dev`, Docker socket), privileged-container
misconfig (Dockerfile asserts no `--privileged`/socket mount).
Mitigations: default-deny policy, deny-wins, canonicalized paths, exact
program matching, network allowlist, `[REDACTED]` audit, approval gates.
Known limits: Windows ref impl is advisory (no kernel sandbox); no resource
limits yet; no redirect/rebinding inspection — runtime fetch guard still needed.
Enforcement rule (P6): every DENY is tested both as policy decision AND as
real blocked IO (no contents returned, no canary file created, audit=BLOCKED).
