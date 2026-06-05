$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$scriptName = "weather_direction_retest_sim.py"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$scriptName*" }

if ($procs) {
  Write-Host "Weather direction retest: RUNNING"
  $procs | Select-Object ProcessId, CommandLine | Format-Table -AutoSize
} else {
  Write-Host "Weather direction retest: STOPPED"
}

Write-Host ""
Write-Host "=== Recent console ==="
Get-Content (Join-Path $workdir "weather_direction_retest_console.log") -Encoding UTF8 -Tail 20 -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Recent errors ==="
Get-Content (Join-Path $workdir "weather_direction_retest_error.log") -Encoding UTF8 -Tail 20 -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Recent simulated trades ==="
Get-Content (Join-Path $workdir "weather_direction_retest_sim.csv") -Encoding UTF8 -Tail 10 -ErrorAction SilentlyContinue
