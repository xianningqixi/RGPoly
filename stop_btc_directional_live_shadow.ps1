$pattern = "btc_directional_live_shadow_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped BTC directional live shadow validator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No BTC directional live shadow validator process found."
}
