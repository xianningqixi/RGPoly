$pattern = "btc_yes_candidate_observation_copy_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped BTC Yes candidate observation copy simulator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No BTC Yes candidate observation copy simulator process found."
}
