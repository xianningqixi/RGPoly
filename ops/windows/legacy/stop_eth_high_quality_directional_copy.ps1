$pattern = "eth_high_quality_directional_copy_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped ETH high-quality directional copy simulator PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No ETH high-quality directional copy simulator process found."
}
