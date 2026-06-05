$pattern = "live_order_preflight.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped live order preflight PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No live order preflight process found."
}
