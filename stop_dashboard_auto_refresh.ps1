$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$pidFile = Join-Path $workdir "dashboard_auto_refresh.pid"

if (!(Test-Path $pidFile)) {
  Write-Host "Dashboard auto refresh is not running."
  exit 0
}

$pidValue = Get-Content $pidFile -ErrorAction SilentlyContinue
if ($pidValue) {
  $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
  if ($proc) {
    Stop-Process -Id $pidValue
    Write-Host "Stopped dashboard auto refresh. PID: $pidValue"
  } else {
    Write-Host "PID file existed, but process was not running."
  }
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
