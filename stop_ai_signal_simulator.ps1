$pattern = "ai_signal_simulator.py"
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*$pattern*" } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId
    Write-Host "Stopped AI signal simulator PID $($_.ProcessId)"
  }
