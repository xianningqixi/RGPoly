$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$consoleLog = Join-Path $workdir "btc_signal_console.log"
$errorLog = Join-Path $workdir "btc_signal_error.log"
$tradesLog = Join-Path $workdir "btc_signal_trades.csv"
$alertFile = Join-Path $workdir "latest_btc_signal.txt"

Write-Host "=== Running BTC signal processes ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*btc_signal_bot.py*" } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "No BTC signal Python process is running."
}

Write-Host ""
Write-Host "=== Recent BTC scan log ==="
if (Test-Path $consoleLog) {
  Get-Content $consoleLog -Tail 20
} else {
  Write-Host "btc_signal_console.log does not exist yet."
}

Write-Host ""
Write-Host "=== Recent BTC errors ==="
if (Test-Path $errorLog) {
  Get-Content $errorLog -Tail 10
} else {
  Write-Host "btc_signal_error.log does not exist yet."
}

Write-Host ""
Write-Host "=== BTC simulated trades ==="
if (Test-Path $tradesLog) {
  Get-Content $tradesLog -Tail 10
} else {
  Write-Host "No BTC simulated trades yet."
}

Write-Host ""
Write-Host "=== Latest BTC signal ==="
if (Test-Path $alertFile) {
  Get-Content $alertFile
} else {
  Write-Host "No BTC signal yet."
}
