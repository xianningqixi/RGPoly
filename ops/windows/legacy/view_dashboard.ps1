$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Set-Location $workdir

Write-Host "Refreshing reports and dashboard..."
python .\generate_dashboard.py --refresh

Write-Host ""
Write-Host "Dashboard:"
Write-Host "$workdir\dashboard.html"
Start-Process "$workdir\dashboard.html"
