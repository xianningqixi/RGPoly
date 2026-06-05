# Polymarket Copytrading Full Stack

Development snapshot for a local Polymarket wallet-copy monitoring system.

This repository is intentionally source-first. Historical logs, generated CSVs,
execution receipts, seen-state files, dashboards, and credential material are
excluded from git.

## What This Project Does

- Discovers and scores public Polymarket wallets.
- Watches public wallet activity through Polymarket data APIs.
- Simulates wallet-copy strategies for BTC, ETH, SOL, BNB, weather, and related
  observation layers.
- Runs final-only PnL and wallet-quality reports.
- Builds live-order preflight rows and manual/external execution tickets.
- Contains optional live CLOB executors, guarded by explicit acknowledgement
  environment variables.

## Safety Defaults

Simulation and reporting scripts do not require private keys.

Live execution scripts must remain disabled unless an operator deliberately sets
credentials and the relevant acknowledgement variable. Do not commit real values
to `.env`, CSV, JSON, Markdown, logs, or Skill snapshots.

Important live gates:

- `POLY_EXECUTION_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`
- `POLY_WALLET_COPY_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`
- `POLY_CLOB_EXECUTION_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`
- `POLY_BTC_COPY_WORKER_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`
- `POLY_BTC_COPY_MONITOR_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`

## Quick Start For Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
python -m compileall -q .
```

Read-only status commands, once runtime CSVs exist locally:

```powershell
.\view_all_status.ps1
python .\summarize_bot_performance.py
python .\execution_layer_status.py
python .\lobster_execution_monitor.py
```

## Repository Layout

- Root `*.py`: strategy simulators, reports, preflight, routers, and optional
  executors. The original project expected these files at root.
- Root `*.ps1`: Windows helper scripts for starting, stopping, and viewing local
  processes.
- `docs/skill/`: Codex Skill metadata and operational references from the
  migration package.
- `docs/legacy/README.original.md`: original read-only arbitrage README retained
  as historical context.
- `.env.example`: placeholder environment names only.

## Data Policy

Runtime data is local-only by default. The `.gitignore` excludes generated CSV,
JSON, JSONL, log, dashboard, receipt, outbox, and seen-state files. Add sanitized
fixtures under an `examples/` directory if tests need stable input data.

## Known Risks

This project contains real-money execution code. Before using live mode, review
`docs/SECURITY.md`, confirm jurisdiction and platform restrictions, use a small
funded wallet, and run dry-run/preflight reports first.
