$pattern = "weather_wallet_copy_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped weather wallet copy simulator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No weather wallet copy simulator process found."
}
