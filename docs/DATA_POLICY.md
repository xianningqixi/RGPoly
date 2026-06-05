# Data Policy

The original migration package contained a large local runtime snapshot. This
development repository intentionally excludes it.

Excluded by default:

- `*_copy_sim.csv`
- `*_trade_audit.csv`
- `*_rejects.csv`
- `*_seen.json`
- `execution_outbox.jsonl`
- `execution_outbox.csv`
- `external_execution_receipts.csv`
- `wallet_copy_exec_log.*`
- generated dashboards
- console and error logs

Use small sanitized fixtures under `examples/` for tests or demos. Do not use
private wallet balances, private receipts, API keys, or personal account state as
fixtures.
