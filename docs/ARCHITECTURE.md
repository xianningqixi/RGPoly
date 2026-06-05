# Architecture

RGPoly v2 is a single Python package for fast local wallet-copy trading.

## Runtime Flow

```text
Polymarket data API
  -> wallet activity normalization
  -> SQLite activity dedupe
  -> token and order-book enrichment
  -> strategy risk checks
  -> order intent
  -> dry-run or live execution receipt
```

## Main Modules

- `rgpoly/config.py`: TOML config model and defaults.
- `rgpoly/polymarket.py`: async public data, Gamma market metadata, and CLOB book client.
- `rgpoly/strategies/wallet_copy.py`: watched-wallet copy strategy.
- `rgpoly/risk.py`: freshness, price, liquidity, exposure, and keyword checks.
- `rgpoly/store.py`: SQLite WAL schema for activity, signals, intents, and receipts.
- `rgpoly/execution.py`: dry-run receipts and guarded live CLOB orders.
- `rgpoly/cli.py`: operator commands and the continuous run loop.
- `rgpoly/dashboard.py`: static local HTML dashboard and CSV export.

## Execution Modes

- `manual`: create intents only.
- `dry_run`: create intents and immediately write dry-run receipts.
- `live`: create intents and submit them to the Polymarket CLOB client.

Live mode is intentionally explicit. It requires `execution.mode = "live"` or
`run --live`, valid CLOB credentials, and
`RGPOLY_LIVE_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK`.

## State Model

Runtime state is local SQLite under `.runtime/rgpoly.sqlite` by default. The
schema uses idempotent primary keys so repeated polling does not duplicate the
same source wallet trade or order intent.

`intents` include market execution metadata (`tick_size`, `neg_risk`) because
the CLOB order builder needs those fields to submit orders correctly across
market types.
