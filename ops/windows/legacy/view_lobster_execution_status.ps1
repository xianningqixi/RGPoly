$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Set-Location $workdir
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== Lobster/OpenClaw execution monitor ==="
python .\lobster_execution_monitor.py

Write-Host "`nReport files:"
Write-Host "$workdir\lobster_execution_monitor.md"
Write-Host "$workdir\lobster_execution_monitor.csv"
