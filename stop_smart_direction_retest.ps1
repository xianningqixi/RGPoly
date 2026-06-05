$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Set-Location $workdir

$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*smart_direction_retest_trade_audit.csv*" -or $_.CommandLine -like "*smart_direction_retest_sim.csv*" }

if (-not $processes) {
  Write-Host "No smart direction retest simulator process found."
  exit 0
}

foreach ($proc in $processes) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped smart direction retest simulator PID $($proc.ProcessId)"
}
