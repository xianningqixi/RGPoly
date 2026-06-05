# Data Policy

RGPoly keeps runtime state local by default.

Excluded from git:

- `.runtime/`
- `.env`
- SQLite databases and WAL files
- logs
- generated dashboards
- exported CSV files
- live order receipts or account snapshots

Tests should use synthetic rows only. Do not add private wallet balances,
private receipts, API credentials, or personal account state as fixtures.
