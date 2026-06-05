$pattern = "weather_high_prob_wallet_copy_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped weather high-prob wallet copy simulator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No weather high-prob wallet copy simulator process found."
}
