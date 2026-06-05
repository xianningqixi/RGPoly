$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$consoleLog = Join-Path $workdir "smart_wallet_copy_console.log"
$tradeLog = Join-Path $workdir "smart_wallet_copy_sim.csv"
$alertFile = Join-Path $workdir "latest_smart_wallet_copy_alert.txt"

Write-Host "=== Running smart wallet copy simulator ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*smart_wallet_copy_sim.py*" } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "No smart wallet copy process is running."
}

Write-Host ""
Write-Host "=== Recent smart wallet copy log ==="
if (Test-Path $consoleLog) {
  Get-Content $consoleLog -Tail 20
} else {
  Write-Host "No console log yet."
}

Write-Host ""
Write-Host "=== Recent smart wallet simulated trades ==="
if (Test-Path $tradeLog) {
  Get-Content $tradeLog -Tail 15
} else {
  Write-Host "No smart wallet copy trades yet."
}

Write-Host ""
Write-Host "=== Latest smart wallet copy alert ==="
if (Test-Path $alertFile) {
  Get-Content $alertFile
} else {
  Write-Host "No alert yet."
}
