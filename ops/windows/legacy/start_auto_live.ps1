if ($env:POLY_EXECUTION_ENABLED -ne "I_UNDERSTAND_REAL_MONEY_RISK") {
  Write-Error "Set POLY_EXECUTION_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK before live execution."
  exit 1
}

python .\polymarket_auto_arb.py `
  --execute `
  --sample-size 500 `
  --interval 8 `
  --min-gross-edge 0.004 `
  --min-net-edge 0.003 `
  --min-total-profit 0.25 `
  --min-shares 10 `
  --max-usdc-per-trade 25 `
  --max-trades 1 `
  --lang zh
