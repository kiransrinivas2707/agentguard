# Security guarantees (v0.2 baseline)

## Guaranteed by AgentGuard (any host)
- Default-deny policy evaluation; deny wins; malformed policy fails closed.
- Exact program matching (`curl.exe`, `/usr/bin/curl` == `curl`; `mycurl` != `curl`).
- Shell-metacharacter denial in string commands; structured list exec without shell.
- Sensitive resource denial + `[REDACTED]` audit (no secret contents in logs/errors).
- Network policy evaluation incl. IP literals, localhost, private ranges,
  `169.254.169.254` metadata blocking.
- Resource limits: timeout + output cap strictly enforced, process-tree kill,
  `RESOURCE_LIMIT` audit. Memory/process-count best-effort here, strict via
  cgroups on Linux.
- Docker config validation rejects privileged, host net/pid, socket mounts,
  dangerous caps.

## Runtime-dependent (need Linux/Docker for strictness)
- Filesystem / process / network isolation, kernel restrictions (namespaces,
  seccomp, Landlock, cgroups), resource memory/process ceilings.
- Windows ref impl is advisory: policy + guards run in-process; a caller that
  bypasses `GuardedSandbox` is not constrained by the OS.

## Not currently guaranteed
- Container escape prevention vs unknown kernel bugs; DNS rebinding/redirect
  inspection; malicious kernel or compromised Docker/host; side-channel or
  resource exhaustion below configured floors.

Skipped test note: symlink-escape test skips only when the OS denies symlink
creation (Windows privilege); Linux CI covers it.
