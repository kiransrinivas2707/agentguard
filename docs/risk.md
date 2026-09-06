# Risk scoring (P5 — deterministic, documented)

`PolicyEngine.risk_score(events)` in `agentguard/policy.py`:

```
ALLOWED read +5 | write +15 | exec low +5 | exec install +15 | network +10
BLOCKED any +5, plus +15 more if CRITICAL secret attempt (=20 total)
APPROVAL flag +20
score = min(sum, 100)
0-29 LOW, 30-59 MEDIUM, 60-84 HIGH, 85-100 CRITICAL
```

Demo (10 scenarios: 4 allowed file/exec/net + 5 blocked incl. 2 secrets + 1 approval)
scores 65/100 HIGH. Same input always gives same score; weights live in
`RISK_TABLE` and are covered by the dashboard + report.
