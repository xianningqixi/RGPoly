$ErrorActionPreference = "Stop"
$skillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$projectRoot = Split-Path -Parent (Split-Path -Parent $skillDir)
Set-Location $projectRoot

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

python .\runtime_strategy_status.py
python .\current_config_report.py --once
python .\pre_live_validation_report.py
python .\strict_simulation_report.py
python .\api_key_readiness_check.py
python .\polymarket_deposit_wallet_readiness.py
python .\execution_intent_router.py --once
python .\execution_layer_status.py

Write-Host ""
Write-Host "Manual preflight candidates:"
if (Test-Path .\live_order_intents.csv) {
  Import-Csv .\live_order_intents.csv |
    Where-Object { $_.status -eq "PREVIEW_ONLY_WOULD_PLACE" } |
    Select-Object ts,source_strategy,wallet_name,outcome,intended_stake_usdc,sim_fill_price,total_cost_usdc,slippage_bps,url |
    Format-Table -AutoSize
} else {
  Write-Host "No live_order_intents.csv found."
}
