$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "btc_candidate_discovery_scheduler_console.log"
$stderr = Join-Path $workdir "btc_candidate_discovery_scheduler_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
$command = "`$env:PYTHONUTF8 = '1'; chcp 65001 > `$null; Set-Location -LiteralPath '$workdir'; python -u .\btc_candidate_discovery_scheduler.py --interval-sec 1800 --public-market-pages 8 --max-public-markets 40 --enrich-top 60"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "BTC candidate discovery scheduler started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
