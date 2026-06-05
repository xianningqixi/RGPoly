$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$consoleLog = Join-Path $workdir "creamcream_copy_console.log"
$tradeLog = Join-Path $workdir "creamcream_copy_sim.csv"
$alertFile = Join-Path $workdir "latest_creamcream_copy_alert.txt"

Write-Host "=== Running CreamCream copy simulator ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*creamcream_copy_sim.py*" } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "No CreamCream copy simulator process is running."
}

Write-Host ""
Write-Host "=== Recent copy simulator log ==="
if (Test-Path $consoleLog) {
  Get-Content $consoleLog -Tail 20
} else {
  Write-Host "No console log yet."
}

Write-Host ""
Write-Host "=== Recent simulated copy trades ==="
if (Test-Path $tradeLog) {
  Get-Content $tradeLog -Tail 15
} else {
  Write-Host "No simulated copy trades yet."
}

Write-Host ""
Write-Host "=== Latest copy alert ==="
if (Test-Path $alertFile) {
  Get-Content $alertFile
} else {
  Write-Host "No copy alert yet."
}
