$scriptName = "eth_directional_wallet_copy_sim.py"
$processes = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$scriptName*" }
foreach ($proc in $processes) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped ETH directional copy simulator PID $($proc.ProcessId)"
}
if (-not $processes) { Write-Host "ETH directional copy simulator is not running." }
