$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "=== Live order preflight process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*live_order_preflight.py*" } |
  Select-Object ProcessId,CommandLine |
  Format-Table -AutoSize

Write-Host "`n=== Recent live order intents ==="
$intents = Join-Path $workdir "live_order_intents.csv"
if (Test-Path $intents) {
  Import-Csv $intents | Select-Object -Last 20 | Format-Table ts,source_strategy,status,reason,outcome,intended_stake_usdc,sim_fill_price,would_live_fill,title -AutoSize
} else {
  Write-Host "No live_order_intents.csv yet."
}

Write-Host "`n=== Recent console ==="
$console = Join-Path $workdir "live_order_preflight_console.log"
if (Test-Path $console) { Get-Content $console -Encoding UTF8 -Tail 20 } else { Write-Host "No console log yet." }

Write-Host "`n=== Recent errors ==="
$errors = Join-Path $workdir "live_order_preflight_error.log"
if ((Test-Path $errors) -and ((Get-Item $errors).Length -gt 0)) { Get-Content $errors -Encoding UTF8 -Tail 20 } else { Write-Host "No errors." }
