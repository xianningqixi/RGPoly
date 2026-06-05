$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "dry_run_console.log"
$stderr = Join-Path $workdir "dry_run_error.log"
$arbLog = Join-Path $workdir "dry_run_arb_log.csv"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$workdir\start_auto_dry_run.ps1`"" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Dry-run monitor started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
Write-Host "Arbitrage log: $arbLog"
