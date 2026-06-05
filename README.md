# RGPoly

Fast local Polymarket wallet-copy trading engine for self-use.

This repository is now v2 only. The legacy script stack, CSV simulators,
frontend folder, old Skill material, and historical helper scripts were removed
so the project has one runtime path:

```text
watched wallet activity -> signal -> risk check -> order intent -> receipt
```

## Why Live Did Not Place Orders Before

The previous v2 rewrite had a live CLOB executor, but `rgpoly run` only polled
wallets and created ready intents. You had to run `rgpoly execute --live`
separately, so a long-running process looked alive while never sending orders.

`rgpoly run` now supports execution modes:

- `manual`: poll only; ready intents wait for manual execution.
- `dry_run`: poll and immediately mark ready intents as dry-run receipts.
- `live`: poll and immediately submit ready intents to Polymarket CLOB.

Default mode is still `dry_run`. Real-money mode requires both `--live` or
`execution.mode = "live"` and the explicit acknowledgement environment gate.

## Layout

```text
rgpoly/                   Trading engine package
  strategies/             Wallet-copy strategy implementation
config/                   Example TOML config
docs/                     Current v2 architecture, security, and data policy
ops/windows/              Start, stop, and status helpers
tests/                    Unit tests for config, store, risk, execution, dashboard
```

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
```

Create local config and database:

```powershell
python -m rgpoly init-config --path .\config\rgpoly.toml
python -m rgpoly --config .\config\rgpoly.toml migrate
python -m rgpoly --config .\config\rgpoly.toml doctor
```

## Dry-Run Operation

Poll once:

```powershell
python -m rgpoly --config .\config\rgpoly.toml poll-once
python -m rgpoly --config .\config\rgpoly.toml intents
python -m rgpoly --config .\config\rgpoly.toml status
```

Run continuously in dry-run mode:

```powershell
python -m rgpoly --config .\config\rgpoly.toml run --dry-run
```

Generate the local dashboard:

```powershell
python -m rgpoly --config .\config\rgpoly.toml dashboard --output .\.runtime\rgpoly_dashboard.html
```

## Live Operation

Set credentials in your shell. Do not commit real values.

```powershell
$env:PRIVATE_KEY="..."
$env:POLY_API_KEY="..."
$env:POLY_API_SECRET="..."
$env:POLY_API_PASSPHRASE="..."
$env:POLY_SIGNATURE_TYPE="3"
$env:POLY_PROXY_ADDRESS="0x..."
```

If you only have a private key, derive Polymarket L2 API credentials:

```powershell
python -m rgpoly --config .\config\rgpoly.toml derive-api-key
```

Enable the live acknowledgement gate and preflight:

```powershell
$env:RGPOLY_LIVE_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"
python -m rgpoly --config .\config\rgpoly.toml doctor --live --check-client
```

Start live execution with a small per-loop cap:

```powershell
python -m rgpoly --config .\config\rgpoly.toml run --live --execute-limit 1
```

Equivalent Windows background helper:

```powershell
.\ops\windows\start_rgpoly_v2.ps1 -Config config\rgpoly.toml -Mode live -ExecuteLimit 1
.\ops\windows\view_rgpoly_v2_status.ps1 -Config config\rgpoly.toml -Mode live
.\ops\windows\stop_rgpoly_v2.ps1
```

## Config

Key execution settings live under `[execution]`:

```toml
mode = "dry_run"             # manual | dry_run | live
execute_limit_per_loop = 10
max_daily_usdc = 50.0
max_open_intents = 25
tick_size = "0.01"
default_neg_risk = false
order_type = "FOK"           # FOK | FAK
```

Wallet-copy strategies are configured with watched wallets, stake size, max
price, freshness window, keyword filters, allowed outcomes, ask-depth checks,
and source-to-ask gap controls.

## Operator Commands

```powershell
python -m rgpoly --config .\config\rgpoly.toml doctor
python -m rgpoly --config .\config\rgpoly.toml run --manual
python -m rgpoly --config .\config\rgpoly.toml run --dry-run
python -m rgpoly --config .\config\rgpoly.toml run --live --execute-limit 1
python -m rgpoly --config .\config\rgpoly.toml execute
python -m rgpoly --config .\config\rgpoly.toml execute --live --limit 1
python -m rgpoly --config .\config\rgpoly.toml export-csv --table receipts --output .\.runtime\receipts.csv
```

## Safety

Use a dedicated low-balance wallet. Start with `--execute-limit 1` and small
`stake_usdc`. Confirm platform eligibility, jurisdiction, and market rules
before live trading. The engine is software, not financial advice.

Useful references:

- Polymarket CLOB order docs: https://docs.polymarket.com/developers/CLOB/orders/create-order
- Polymarket L2 client docs: https://docs.polymarket.com/developers/CLOB/clients/methods-l2
