$pattern = "bond_style_market_scanner.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$pattern*" }
foreach ($proc in $procs) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped bond-style scanner PID $($proc.ProcessId)"
}
if (-not $procs) {
  Write-Host "No bond-style scanner process found."
}
