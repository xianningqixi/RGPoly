$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "=== Weather high-prob live shadow process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*weather_high_prob_live_shadow_sim.py*" } |
  Select-Object ProcessId,CommandLine |
  Format-Table -AutoSize

Write-Host "`n=== Recent console ==="
$console = Join-Path $workdir "weather_high_prob_live_shadow_console.log"
if (Test-Path $console) { Get-Content $console -Encoding UTF8 -Tail 20 } else { Write-Host "No console log yet." }

Write-Host "`n=== Recent errors ==="
$errors = Join-Path $workdir "weather_high_prob_live_shadow_error.log"
if ((Test-Path $errors) -and ((Get-Item $errors).Length -gt 0)) { Get-Content $errors -Encoding UTF8 -Tail 20 } else { Write-Host "No errors." }

Write-Host "`n=== Recent shadow trades ==="
$trades = Join-Path $workdir "weather_high_prob_live_shadow_sim.csv"
if (Test-Path $trades) { Import-Csv $trades | Select-Object -Last 10 | Format-Table -AutoSize } else { Write-Host "No shadow trades yet." }
