$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "=== Weather high-prob wallet copy process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*weather_high_prob_wallet_copy_sim.py*" } |
  Select-Object ProcessId,CommandLine |
  Format-Table -AutoSize

Write-Host "`n=== Recent console ==="
$console = Join-Path $workdir "weather_high_prob_wallet_copy_console.log"
if (Test-Path $console) { Get-Content $console -Encoding UTF8 -Tail 20 } else { Write-Host "No console log yet." }

Write-Host "`n=== Recent errors ==="
$errors = Join-Path $workdir "weather_high_prob_wallet_copy_error.log"
if ((Test-Path $errors) -and ((Get-Item $errors).Length -gt 0)) { Get-Content $errors -Encoding UTF8 -Tail 20 } else { Write-Host "No errors." }

Write-Host "`n=== Recent simulated trades ==="
$trades = Join-Path $workdir "weather_high_prob_wallet_copy_sim.csv"
if (Test-Path $trades) { Import-Csv $trades | Select-Object -Last 10 | Format-Table -AutoSize } else { Write-Host "No simulated trades yet." }
