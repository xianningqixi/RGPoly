$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "weather_high_prob_wallet_copy_console.log"
$stderr = Join-Path $workdir "weather_high_prob_wallet_copy_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
$command = "`$env:PYTHONUTF8 = '1'; chcp 65001 > `$null; Set-Location -LiteralPath '$workdir'; python -u .\weather_high_prob_wallet_copy_sim.py --strategy-key weather_high_prob_wallet_copy --live-only --stake-usdc 10 --observation-stake-usdc 10 --bankroll-usdc 1000 --interval 10 --activity-limit 100 --allowed-wallet Poligarch --allowed-wallet Railbird --allowed-price-bucket 0.8-0.9 --allowed-price-bucket 0.9-1.0 --allowed-wallet-direction Poligarch=No:0.9-1.0 --allowed-wallet-direction Poligarch=Yes:0.8-0.9 --allowed-wallet-direction Poligarch=Yes:0.9-1.0 --allowed-wallet-direction Railbird=No:0.9-1.0 --wallet-direction-q Poligarch=No:0.9-1.0:0.98373984 --wallet-direction-q Poligarch=Yes:0.8-0.9:0.94915254 --wallet-direction-q Poligarch=Yes:0.9-1.0:1.0 --wallet-direction-q Railbird=No:0.9-1.0:1.0 --min-direction-edge 0.005 --min-source-usdc 1 --min-source-price 0.80 --max-source-price 0.995 --min-entry-price 0.80 --max-entry-price 0.995 --max-slippage-bps 150 --max-source-to-ask-gap 0.010 --max-source-age-sec 60 --min-ask-depth-usdc 20 --max-market-stake-usdc 10 --max-event-stake-usdc 20 --max-wallet-market-entries 1 --max-open-positions 100 --mark-every-scans 30 --log .\weather_high_prob_wallet_copy_sim.csv --audit-log .\weather_high_prob_trade_audit.csv --reject-log .\weather_high_prob_rejects.csv --seen .\weather_high_prob_seen.json --alert-file .\latest_weather_high_prob_wallet_copy_alert.txt"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Weather high-prob wallet copy simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
