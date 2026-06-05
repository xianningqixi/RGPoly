$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "=== BTC candidate discovery scheduler process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*btc_candidate_discovery_scheduler.py*" } |
  Select-Object ProcessId,CommandLine |
  Format-Table -AutoSize

Write-Host "`n=== Scheduler status ==="
$status = Join-Path $workdir "btc_candidate_discovery_scheduler_status.txt"
if (Test-Path $status) {
  Get-Content $status -Encoding UTF8 -Tail 5
} else {
  Write-Host "No scheduler status yet."
}

Write-Host "`n=== Recent scheduler log ==="
$log = Join-Path $workdir "btc_candidate_discovery_scheduler.log"
if (Test-Path $log) {
  Get-Content $log -Encoding UTF8 -Tail 40
} else {
  Write-Host "No scheduler log yet."
}

Write-Host "`n=== Recent errors ==="
$errors = Join-Path $workdir "btc_candidate_discovery_scheduler_error.log"
if ((Test-Path $errors) -and ((Get-Item $errors).Length -gt 0)) {
  Get-Content $errors -Encoding UTF8 -Tail 30
} else {
  Write-Host "No errors."
}
