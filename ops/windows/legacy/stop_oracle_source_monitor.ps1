$pattern = "oracle_source_monitor.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped oracle source monitor PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No oracle source monitor process found."
}
