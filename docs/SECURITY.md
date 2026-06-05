# Security Notes

This repository is prepared as a development snapshot. Treat all trading code as
high risk.

## Included Safety Changes

- `openclaw_outbox_executor.py` no longer falls back to a private key file in the
  user's home directory.
- `openclaw_outbox_executor.py` requires
  `POLY_CLOB_EXECUTION_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK` for `--execute`.
- `polymarket_btc_copy_worker.py` and
  `polymarket_btc_copy_worker_daemon.py` require
  `POLY_BTC_COPY_WORKER_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK` before live
  execution.
- `polymarket_btc_copy_monitor.py` requires
  `POLY_BTC_COPY_MONITOR_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK` before live
  execution.
- `wallet_copy_executor.py` has a continuous-loop logging bug fixed so processed
  IDs are saved after a live result instead of failing on an undefined variable.
- `install_polymarket_worker_task.ps1` now parses as PowerShell and documents the
  live worker acknowledgement gate.

## Never Commit

- Private keys or seed phrases.
- Polymarket API key, secret, or passphrase.
- `.env` files with real values.
- Execution receipts from a real account.
- Runtime outbox files, seen-state files, local dashboards, and logs.

## Live Execution Checklist

1. Use a dedicated low-balance wallet.
2. Confirm all strategy filters and outbox contents.
3. Run preflight and dry-run first.
4. Set only the execution gate for the exact executor you intend to run.
5. Limit `--max-trades` and `--max-usdc`.
6. Monitor `external_execution_receipts.csv` separately from simulated PnL.

Simulation PnL, external execution receipts, and redeem-confirmed realized PnL
must be reported separately.
