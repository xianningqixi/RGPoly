# Security Notes

RGPoly can submit real-money Polymarket CLOB orders in live mode. Treat the
entire runtime as high risk.

## Live Gate

Live execution requires all of the following:

- `run --live` or `execution.mode = "live"`.
- `RGPOLY_LIVE_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`.
- `PRIVATE_KEY`.
- `POLY_API_KEY`, `POLY_API_SECRET`, and `POLY_API_PASSPHRASE`.
- Correct `POLY_SIGNATURE_TYPE` and, when needed, `POLY_PROXY_ADDRESS`.

Run this before live trading:

```powershell
python -m rgpoly --config .\config\rgpoly.toml doctor --live --check-client
```

## Never Commit

- Private keys, seed phrases, or wallet export files.
- Polymarket API key, secret, or passphrase.
- `.env` files with real values.
- Local SQLite databases.
- Live receipts, order IDs, account balances, logs, or dashboards.

## Live Checklist

1. Confirm you are allowed to trade on the platform from your jurisdiction.
2. Use a dedicated low-balance wallet.
3. Start in dry-run mode and inspect rejects, intents, and receipts.
4. Keep `stake_usdc`, `max_daily_usdc`, and `--execute-limit` small.
5. Run `doctor --live --check-client`.
6. Watch the terminal and `.runtime` database while live mode is active.
