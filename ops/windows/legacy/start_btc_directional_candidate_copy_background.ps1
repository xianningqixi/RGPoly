$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "btc_directional_candidate_copy_console.log"
$stderr = Join-Path $workdir "btc_directional_candidate_copy_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
$command = "`$env:PYTHONUTF8 = '1'; chcp 65001 > `$null; Set-Location -LiteralPath '$workdir'; python .\btc_directional_candidate_rotation_report.py --once; python .\candidate_sampling_health.py --once; python .\apply_btc_candidate_rotation.py --once; python -u .\btc_directional_candidate_copy_sim.py --strategy-key btc_directional_candidate_copy --wallet-candidates .\btc_directional_candidate_pool.csv --candidate-limit 12 --reload-wallets-each-scan --stake-usdc 10 --bankroll-usdc 1000 --interval 12 --live-only --allowed-outcome No --block-market-keyword reach --block-market-keyword dip --max-price 0.80 --max-slippage-bps 200 --max-source-to-ask-gap 0.015 --max-source-age-sec 90 --min-source-usdc 3 --min-ask-depth-usdc 20 --max-market-stake-usdc 10 --max-wallet-market-entries 1 --max-open-positions 100 --max-hours-to-end 36 --log .\btc_directional_candidate_copy_sim.csv --audit-log .\btc_directional_candidate_trade_audit.csv --reject-log .\btc_directional_candidate_rejects.csv --seen .\btc_directional_candidate_seen.json --alert-file .\latest_btc_directional_candidate_copy_alert.txt"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "BTC directional candidate copy simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"

