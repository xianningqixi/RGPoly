$pattern = "execution_intent_router.py"
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*$pattern*" } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    Write-Host "Stopped execution intent router PID $($_.ProcessId)"
  }

