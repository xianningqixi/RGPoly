$pattern = "btc_directional_candidate_copy_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped BTC directional candidate copy simulator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No BTC directional candidate copy simulator process found."
}
