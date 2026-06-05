$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "=== Oracle source process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*oracle_source_monitor.py*" } |
  Select-Object ProcessId,CommandLine |
  Format-Table -AutoSize

Write-Host "`n=== Recent console ==="
$console = Join-Path $workdir "oracle_source_console.log"
if (Test-Path $console) {
  Get-Content $console -Encoding UTF8 -Tail 12
} else {
  Write-Host "No console log yet."
}

Write-Host "`n=== Recent errors ==="
$errors = Join-Path $workdir "oracle_source_error.log"
if ((Test-Path $errors) -and ((Get-Item $errors).Length -gt 0)) {
  Get-Content $errors -Encoding UTF8 -Tail 12
} else {
  Write-Host "No errors."
}

Write-Host "`n=== Recent oracle sources ==="
$map = Join-Path $workdir "oracle_source_map.csv"
if (Test-Path $map) {
  Import-Csv $map | Select-Object -Last 10 slug,category,resolution_source,source_url,key_metric,precision | Format-Table -AutoSize
} else {
  Write-Host "No oracle source map yet."
}
