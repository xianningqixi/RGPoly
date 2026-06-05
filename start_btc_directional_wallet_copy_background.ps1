$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "btc_directional_copy_console.log"
$stderr = Join-Path $workdir "btc_directional_copy_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
$command = "`$env:PYTHONUTF8 = '1'; chcp 65001 > `$null; Set-Location -LiteralPath '$workdir'; python -u .\btc_directional_wallet_copy_sim.py --strategy-key btc_directional_copy --stake-usdc 10 --bankroll-usdc 1000 --interval 10 --live-only --min-price 0.05 --max-price 0.99 --yes-max-price 0.99 --max-slippage-bps 800 --max-source-to-ask-gap 0.060 --max-source-age-sec 180 --min-source-usdc 1 --min-ask-depth-usdc 10 --max-market-stake-usdc 20 --max-wallet-market-entries 2 --max-open-positions 100 --max-hours-to-end 120"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "BTC directional wallet copy simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"

