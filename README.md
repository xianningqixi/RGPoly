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

## RGPoly v2 Rewrite

The `rgpoly/` package is the new fast self-use engine. It is designed to run
beside the legacy scripts while the trading path is migrated.

Key differences from the legacy script stack:

- SQLite WAL state store instead of many append-only CSV files.
- Async Polymarket API polling for watched-wallet activity and order books.
- One normalized path: activity -> signal -> risk check -> order intent -> receipt.
- Config-driven multi-strategy wallet-copy migration for BTC directional,
  crypto short-window, and selected weather wallets.
- Dry-run execution is the default. Live CLOB execution is implemented but
  requires an explicit acknowledgement gate.

Create a local config and state database:

```powershell
python -m rgpoly init-config --path .\config\rgpoly.toml
python -m rgpoly --config .\config\rgpoly.toml migrate
```

Poll watched wallets once:

```powershell
python -m rgpoly --config .\config\rgpoly.toml poll-once
python -m rgpoly --config .\config\rgpoly.toml intents
python -m rgpoly --config .\config\rgpoly.toml status
```

Run continuously:

```powershell
python -m rgpoly --config .\config\rgpoly.toml run
```

On Windows, start/stop/view the v2 engine with:

```powershell
.\ops\windows\start_rgpoly_v2.ps1 -Config config\rgpoly.toml
.\ops\windows\view_rgpoly_v2_status.ps1 -Config config\rgpoly.toml
.\ops\windows\stop_rgpoly_v2.ps1
```

Process ready intents as dry-run receipts:

```powershell
python -m rgpoly --config .\config\rgpoly.toml execute
```

Generate a local SQLite-backed dashboard:

```powershell
python -m rgpoly --config .\config\rgpoly.toml dashboard --output .\.runtime\rgpoly_dashboard.html
```

Live CLOB execution is gated separately from the legacy scripts:

```powershell
$env:RGPOLY_LIVE_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"
python -m rgpoly --config .\config\rgpoly.toml execute --live --limit 1
```

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
