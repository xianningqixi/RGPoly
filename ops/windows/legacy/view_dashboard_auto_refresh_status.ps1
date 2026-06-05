$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$pidFile = Join-Path $workdir "dashboard_auto_refresh.pid"
$logFile = Join-Path $workdir "dashboard_auto_refresh.log"
$errorFile = Join-Path $workdir "dashboard_auto_refresh_error.log"

Write-Host "=== Dashboard auto refresh ==="
if (Test-Path $pidFile) {
  $pidValue = Get-Content $pidFile -ErrorAction SilentlyContinue
  $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
  if ($proc) {
    Write-Host "Status: RUNNING"
    Write-Host "PID: $pidValue"
  } else {
    Write-Host "Status: STOPPED stale pid=$pidValue"
  }
} else {
  Write-Host "Status: STOPPED"
}

Write-Host "Dashboard: $workdir\dashboard.html"
Write-Host ""

Write-Host "=== Recent refresh log ==="
if (Test-Path $logFile) {
  Get-Content $logFile -Encoding UTF8 -Tail 20
} else {
  Write-Host "No refresh log yet."
}

Write-Host ""
Write-Host "=== Recent refresh errors ==="
if (Test-Path $errorFile) {
  Get-Content $errorFile -Encoding UTF8 -Tail 20
} else {
  Write-Host "No refresh error log yet."
}
