$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Set-Location $workdir

Write-Host "=== Smart direction retest process ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*smart_direction_retest_trade_audit.csv*" -or $_.CommandLine -like "*smart_direction_retest_sim.csv*" } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "Not running."
}

Write-Host ""
Write-Host "=== Recent console ==="
if (Test-Path .\smart_direction_retest_console.log) {
  Get-Content .\smart_direction_retest_console.log -Encoding UTF8 -Tail 15
} else {
  Write-Host "No console log yet."
}

Write-Host ""
Write-Host "=== Recent errors ==="
if (Test-Path .\smart_direction_retest_error.log) {
  $errors = Get-Content .\smart_direction_retest_error.log -Encoding UTF8 -Tail 15
  if ($errors) { $errors } else { Write-Host "No errors." }
} else {
  Write-Host "No error log yet."
}

Write-Host ""
Write-Host "=== Recent simulated trades ==="
if (Test-Path .\smart_direction_retest_sim.csv) {
  Import-Csv .\smart_direction_retest_sim.csv | Select-Object -Last 10 ts,wallet_name,outcome,window,source_price,sim_entry_price,stake,status,pnl,title | Format-Table -AutoSize -Wrap
} else {
  Write-Host "No simulated trades yet."
}
