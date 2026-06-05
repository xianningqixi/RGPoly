# Polymarket Read-Only Arbitrage Monitor

This is a read-only Polymarket basket-arbitrage scanner. It does not place
orders, does not need API keys, and does not touch wallets.

It scans active CLOB markets and looks for cases where buying one share of
every outcome costs less than the guaranteed 1 USDC redemption value.

## Quick Start

Install the official execution client:

```powershell
python -m pip install -r .\requirements.txt
```

Read-only monitor:

```powershell
python .\scan_polymarket_arbitrage.py --sample-size 500 --min-net-edge 0.001 --min-shares 10
```

Continuous monitoring:

```powershell
python .\scan_polymarket_arbitrage.py --loop --interval 10 --sample-size 500 --min-net-edge 0.001 --min-shares 10 --csv .\opportunities.csv
```

Test the local calculation model:

```powershell
python .\scan_polymarket_arbitrage.py --self-test
```

Dry-run auto executor:

```powershell
.\start_auto_dry_run.ps1
```

Live auto executor:

```powershell
$env:POLY_PRIVATE_KEY="0x..."
$env:POLY_PROXY_ADDRESS="0x..."       # if your Polymarket account uses a proxy wallet
$env:POLY_SIGNATURE_TYPE="1"          # set only if required by your account type
$env:POLY_API_KEY="..."
$env:POLY_API_SECRET="..."
$env:POLY_API_PASSPHRASE="..."
$env:POLY_EXECUTION_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"
.\start_auto_live.ps1
```

The live executor uses FOK market buys. It refreshes the order book immediately
before execution and logs every attempted execution to `auto_arb_log.csv` and
`auto_arb_log.jsonl`.

## What The Scanner Calculates

For a binary market:

```text
edge = 1 - yes_cost - no_cost - estimated_fees
```

For a multi-outcome market:

```text
edge = 1 - sum(all_outcome_costs) - estimated_fees
```

The scanner uses the full ask ladder, not only the best ask. It tests executable
basket sizes across depth and reports the quantity with the highest estimated
total profit.

## Useful Commands

Show only strict candidates:

```powershell
python .\scan_polymarket_arbitrage.py --sample-size 1000 --min-gross-edge 0.003 --min-net-edge 0.001 --min-shares 20
```

Show near misses by allowing negative edge:

```powershell
python .\scan_polymarket_arbitrage.py --sample-size 200 --min-gross-edge -1 --min-net-edge -1 --min-shares 1 --max-rows 10
```

Use a fixed taker-fee assumption:

```powershell
python .\scan_polymarket_arbitrage.py --fee-rate 0.04
```

Run exactly two monitor scans:

```powershell
python .\scan_polymarket_arbitrage.py --loop --max-scans 2 --interval 5
```

## Output Columns

- `net/set`: estimated profit per complete basket after fees.
- `gross`: profit per complete basket before fees.
- `fees`: estimated taker fee per complete basket.
- `qty`: best executable complete-basket quantity across ask depth.
- `profit`: estimated total profit for that quantity.
- `avgcost`: average cost per complete basket before fees.
- `bestasks`: first ask level for each outcome.

## Important Limits

- The executor is real when `--execute` and `POLY_EXECUTION_ENABLED` are both
  set, but multi-leg basket execution is sequential, not atomic.
- FOK protects each leg individually. It cannot guarantee that all legs fill
  together.
- Public opportunities are usually tiny and disappear quickly.
- Fee estimates can be overridden with `--fee-rate`; verify the exact market
  fee before trading.
- Respect Polymarket's geographic restrictions and local law.
