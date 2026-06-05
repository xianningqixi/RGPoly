$pattern = "polymarket_auto_arb.py"

Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*$pattern*" } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    Write-Host "Stopped dry-run process PID=$($_.ProcessId)"
  }
