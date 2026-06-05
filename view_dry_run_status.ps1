$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$consoleLog = Join-Path $workdir "dry_run_console.log"
$arbLog = Join-Path $workdir "dry_run_arb_log.csv"
$alertFile = Join-Path $workdir "latest_arb_alert.txt"

Write-Host "=== Running dry-run processes ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*polymarket_auto_arb.py*" } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "No dry-run Python process is running."
}

Write-Host ""
Write-Host "=== Recent scan log ==="
if (Test-Path $consoleLog) {
  Get-Content $consoleLog -Tail 20
} else {
  Write-Host "dry_run_console.log does not exist yet."
}

Write-Host ""
Write-Host "=== Simulated arbitrage records ==="
if (Test-Path $arbLog) {
  Get-Content $arbLog -Tail 10
} else {
  Write-Host "No simulated arbitrage records yet."
}

Write-Host ""
Write-Host "=== Latest alert ==="
if (Test-Path $alertFile) {
  Get-Content $alertFile
} else {
  Write-Host "No alert yet."
}
