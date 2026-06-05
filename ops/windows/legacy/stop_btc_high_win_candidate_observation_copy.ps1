$target = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*btc_high_win_candidate_observation_copy_sim.py*" }

if (-not $target) {
  Write-Host "BTC high-win candidate observation simulator is not running."
  exit 0
}

$target | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force
  Write-Host "Stopped PID $($_.ProcessId)"
}
