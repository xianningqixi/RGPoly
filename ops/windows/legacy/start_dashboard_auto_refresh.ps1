$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$pidFile = Join-Path $workdir "dashboard_auto_refresh.pid"
$logFile = Join-Path $workdir "dashboard_auto_refresh.log"
$errorFile = Join-Path $workdir "dashboard_auto_refresh_error.log"

Set-Location $workdir

if (Test-Path $pidFile) {
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($oldPid) {
    $oldProc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    if ($oldProc) {
      Write-Host "Dashboard auto refresh is already running. PID: $oldPid"
      Write-Host "Dashboard: $workdir\dashboard.html"
      exit 0
    }
  }
}

if (!(Test-Path ".\dashboard_auto_refresh.py")) {
  Write-Host "Missing dashboard_auto_refresh.py"
  exit 1
}

$proc = Start-Process python -WindowStyle Hidden -ArgumentList "-u .\dashboard_auto_refresh.py" -PassThru
$proc.Id | Set-Content -Path $pidFile -Encoding ASCII

Write-Host "Dashboard auto refresh started. PID: $($proc.Id)"
Write-Host "Refresh interval: 10 minutes"
Write-Host "Dashboard: $workdir\dashboard.html"
Write-Host "Log: $logFile"
