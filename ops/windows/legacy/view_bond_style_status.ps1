$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $workdir

Write-Host "=== Bond-style scanner process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*bond_style_market_scanner.py*" } |
  Select-Object ProcessId, CommandLine |
  Format-Table -Wrap

Write-Host ""
Write-Host "=== Recent bond-style console ==="
if (Test-Path .\bond_style_console.log) {
  Get-Content .\bond_style_console.log -Encoding UTF8 -Tail 20
} else {
  Write-Host "No console log yet."
}

Write-Host ""
Write-Host "=== Recent bond-style errors ==="
if (Test-Path .\bond_style_error.log) {
  Get-Content .\bond_style_error.log -Encoding UTF8 -Tail 20
} else {
  Write-Host "No error log yet."
}

Write-Host ""
Write-Host "=== Latest bond candidates ==="
if (Test-Path .\bond_style_candidates.csv) {
  Import-Csv .\bond_style_candidates.csv |
    Select-Object -Last 10 ts,scan_id,category,outcome,sim_fill_price,spread,hours_to_end,title |
    Format-Table -AutoSize -Wrap
} else {
  Write-Host "No candidates logged yet."
}

Write-Host ""
Write-Host "=== Latest bond alert ==="
if (Test-Path .\latest_bond_style_alert.txt) {
  Get-Content .\latest_bond_style_alert.txt -Encoding UTF8
} else {
  Write-Host "No alert file yet."
}
