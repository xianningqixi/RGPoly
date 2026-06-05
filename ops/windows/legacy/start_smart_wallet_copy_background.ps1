$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "smart_wallet_copy_console.log"
$stderr = Join-Path $workdir "smart_wallet_copy_error.log"

Write-Host "Smart wallet copy simulator is PAUSED."
Write-Host "Reason: finalized audit shows large negative realized ROI after event-market resolution backfill."
Write-Host "No new Smart Wallet copy process was started."
exit 0

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
$command = "`$env:PYTHONUTF8 = '1'; chcp 65001 > `$null; Set-Location -LiteralPath '$workdir'; python -u .\smart_wallet_copy_sim.py --stake-usdc 10 --bankroll-usdc 1000 --interval 10 --windows 5m,15m --live-only --max-slippage-bps 150 --max-source-to-ask-gap 0.01 --max-source-age-sec 6 --min-ask-depth-usdc 30 --max-stake-usdc 10 --max-market-stake-usdc 10 --max-wallet-market-entries 1 --max-open-positions 100 --default-q 0.50 --default-q-min-price 0.35 --default-q-max-price 0.65 --require-positive-ev --min-ev 0.01"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Smart wallet copy simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
