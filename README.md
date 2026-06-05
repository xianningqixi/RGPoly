# Polymarket Copytrading Full Stack

Development snapshot for a local Polymarket wallet-copy monitoring system.

This repository is intentionally source-first. Historical logs, generated CSVs,
execution receipts, seen-state files, dashboards, and credential material are
excluded from git.

## What This Project Does

- Discovers and scores public Polymarket wallets.
- Watches public wallet activity through Polymarket data APIs.
- Simulates wallet-copy strategies for BTC, ETH, SOL, BNB, weather, and smart
  wallet cohorts.
- Runs final-only PnL, wallet-quality, risk, and strategy-health reports.
- Builds live-order preflight rows and manual/external execution tickets.
- Contains optional live CLOB executors, guarded by explicit acknowledgement
  environment variables.

## Repository Layout

```text
backend/
  common/                 Shared audit, risk, settlement, and path helpers
  execution/              Preflight, outbox, API-key, and live execution code
  monitors/               Background health/activity monitors
  reports/                Read-only reporting, backtests, and status views
  research/               Wallet/account discovery and research tools
  strategies/
    ai/                   AI signal simulation
    arbitrage/            Basket and bond-style arbitrage scans
    btc/                  BTC directional/candidate strategies
    crypto/               ETH, SOL, BNB, and lead-lag strategies
    smart_wallets/        Smart-wallet cohort and retest simulations
    weather/              Weather-market strategy simulations
  tools/                  One-off debug and operator utilities

frontend/
  dashboard/              Static dashboard generation

ops/
  windows/legacy/         Original PowerShell start/stop/view helpers

docs/                     Security, data policy, architecture, and Skill docs
examples/                 Sanitized schemas and fixtures
scripts/                  Project-aware launch helpers
```

## Quick Start For Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
python -m compileall -q .
```

Use the project runner for scripts in the reorganized tree. It sets the working
directory to the repository root, exposes all backend/frontend script folders on
`PYTHONPATH`, and sets `POLY_PROJECT_ROOT`.

```powershell
.\scripts\run_python.ps1 backend\reports\runtime_strategy_status.py
.\scripts\run_python.ps1 backend\execution\execution_layer_status.py
.\scripts\run_python.ps1 frontend\dashboard\generate_dashboard.py
```

If local PowerShell policy blocks `.ps1` scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_python.ps1 backend\reports\runtime_strategy_status.py
```

Cross-platform equivalent:

```bash
python scripts/run_python.py backend/reports/runtime_strategy_status.py
```

The original Windows process helpers are kept under `ops/windows/legacy/`.
Treat them as migration references until they are modernized to the new runner.

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

## Runtime Data Policy

Runtime data is local-only by default. The `.gitignore` excludes generated CSV,
JSON, JSONL, log, dashboard, receipt, outbox, and seen-state files. Add sanitized
fixtures under `examples/` if tests need stable input data.

Before using live mode, review `docs/SECURITY.md`, confirm jurisdiction and
platform restrictions, use a small funded wallet, and run dry-run/preflight
reports first.
