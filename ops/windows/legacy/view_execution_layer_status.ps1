$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Set-Location $workdir
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== Execution intent router process ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*execution_intent_router.py*" } |
  Select-Object ProcessId,CommandLine | Format-Table -AutoSize

Write-Host "`n=== Execution layer status ==="
python .\execution_layer_status.py

Write-Host "`n=== Latest manual tickets ==="
if (Test-Path .\manual_order_tickets.md) {
  Get-Content .\manual_order_tickets.md -Tail 80
} else {
  Write-Host "No manual_order_tickets.md yet."
}

