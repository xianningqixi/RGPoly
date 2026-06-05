$scriptName = "weather_direction_retest_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$scriptName*" }

if (-not $procs) {
  Write-Host "Weather direction retest simulator is not running."
  exit 0
}

foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped Weather direction retest PID $($proc.ProcessId)"
}
