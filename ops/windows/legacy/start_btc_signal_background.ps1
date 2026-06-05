$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "btc_signal_console.log"
$stderr = Join-Path $workdir "btc_signal_error.log"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$workdir'; python -u .\btc_signal_bot.py --bankroll-usdc 1000 --stake-usdc 10 --interval 20 --durations 5m,15m --min-move-bps 20 --max-entry-price 0.58 --max-source-spread-bps 4 --min-pm-lag-bps 4 --max-entries-per-market 1 --entry-cooldown 120`"" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "BTC signal simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
