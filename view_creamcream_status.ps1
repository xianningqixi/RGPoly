$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$consoleLog = Join-Path $workdir "creamcream_console.log"
$log = Join-Path $workdir "creamcream_activity.csv"
$alertFile = Join-Path $workdir "latest_creamcream_alert.txt"

Write-Host "=== Running CreamCream watcher ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*watch_creamcream_activity.py*" } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "No CreamCream watcher process is running."
}

Write-Host ""
Write-Host "=== Recent watcher log ==="
if (Test-Path $consoleLog) {
  Get-Content $consoleLog -Tail 20
} else {
  Write-Host "creamcream_console.log does not exist yet."
}

Write-Host ""
Write-Host "=== Recent account activity records ==="
if (Test-Path $log) {
  Get-Content $log -Tail 10
} else {
  Write-Host "No new account activity recorded yet."
}

Write-Host ""
Write-Host "=== Latest account alert ==="
if (Test-Path $alertFile) {
  Get-Content $alertFile
} else {
  Write-Host "No account alert yet."
}
