$pattern = "btc_candidate_discovery_scheduler.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped BTC candidate discovery scheduler PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No BTC candidate discovery scheduler process found."
}
