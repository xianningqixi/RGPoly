$pattern = "weather_high_prob_live_shadow_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped weather high-prob live shadow validator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No weather high-prob live shadow validator process found."
}
