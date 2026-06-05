# Runbook

## Normal Health Check

Run from the project root:

```powershell
.\view_all_status.ps1
python .\summarize_bot_performance.py
python .\lobster_execution_monitor.py
python .\execution_layer_status.py
```

Summarize:

- running processes
- each simulation strategy total/final/pending/W/L/PnL/ROI
- last 24h new trades
- error logs
- OpenClaw/external receipt counts
- unauthorized strategy receipts
- final-only/redeem-confirmed PnL separated from simulation

## Start Key Background Processes

```powershell
.\start_btc_no_dominant_candidate_copy_background.ps1
.\start_btc_high_win_candidate_observation_copy_background.ps1
.\start_btc_yes_candidate_observation_copy_background.ps1
.\start_btc_candidate_discovery_scheduler.ps1
.\start_live_order_preflight_background.ps1
.\start_execution_intent_router_background.ps1
.\start_dashboard_auto_refresh.ps1
```

Use the corresponding `stop_*.ps1` scripts before changing long-running parameters.

## Bitcoin Up/Down 15-Wallet Observation

Wallet list:

`btc_high_win_candidate_wallets.csv`

Status:

```powershell
.\view_btc_high_win_candidate_observation_copy_status.ps1
```

Treat all pending rows as observation only. Upgrade or remove wallets only after final-only samples are available.

## Dashboard

Generate once:

```powershell
python .\generate_dashboard.py
```

Open:

```powershell
.\view_dashboard.ps1
```

Auto-refresh:

```powershell
.\start_dashboard_auto_refresh.ps1
```

## Migration

After restoring a snapshot, run:

```powershell
python .\runtime_strategy_status.py
python .\realized_pnl_report.py
python .\generate_dashboard.py
```

Then start only the processes needed in the new environment.
