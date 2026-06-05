$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$out = Join-Path $workdir "weather_wallet_copy_console.log"
$err = Join-Path $workdir "weather_wallet_copy_error.log"

$env:PYTHONIOENCODING = "utf-8"

Start-Process -FilePath $python `
  -ArgumentList "-u", ".\weather_wallet_copy_sim.py", "--live-only", "--stake-usdc", "10", "--observation-stake-usdc", "10", "--bankroll-usdc", "1000", "--interval", "6", "--activity-limit", "100", "--allowed-wallet", "ColdMath", "--allowed-wallet", "NoonienSoong", "--allowed-wallet", "BeefSlayer", "--min-source-usdc", "1", "--min-entry-price", "0.05", "--max-entry-price", "0.95", "--max-slippage-bps", "250", "--max-source-to-ask-gap", "0.025", "--max-source-age-sec", "120", "--max-market-stake-usdc", "10", "--max-event-stake-usdc", "20", "--max-wallet-market-entries", "1", "--max-open-positions", "100", "--mark-every-scans", "30" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err `
  -WindowStyle Hidden

Write-Host "Weather wallet copy simulator started in background."
Write-Host "Console log: $out"
Write-Host "Error log: $err"
Write-Host "Trades: $(Join-Path $workdir 'weather_wallet_copy_sim.csv')"

