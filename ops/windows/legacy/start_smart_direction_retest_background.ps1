$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "smart_direction_retest_console.log"
$stderr = Join-Path $workdir "smart_direction_retest_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
$command = "`$env:PYTHONUTF8 = '1'; chcp 65001 > `$null; Set-Location -LiteralPath '$workdir'; python -u .\smart_direction_retest_sim.py --log .\smart_direction_retest_sim.csv --audit-log .\smart_direction_retest_trade_audit.csv --seen .\smart_direction_retest_seen.json --alert-file .\latest_smart_direction_retest_alert.txt --stake-usdc 10 --bankroll-usdc 1000 --max-stake-usdc 10 --interval 10 --windows 5m,15m --allowed-outcome Down --allowed-asset BTC --allowed-asset ETH --live-only --min-price 0.10 --max-price 0.50 --max-slippage-bps 120 --max-source-to-ask-gap 0.008 --max-source-age-sec 6 --min-source-usdc 3 --min-ask-depth-usdc 50 --max-market-stake-usdc 10 --max-wallet-market-entries 1 --max-open-positions 100 --default-q 0.52 --default-q-min-price 0.10 --default-q-max-price 0.50 --require-positive-ev --min-ev 0.015 --low-price-reduce-below 0.15 --low-price-stake-factor 0.5 --min-low-price-ask-depth-usdc 150"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Smart direction retest simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
