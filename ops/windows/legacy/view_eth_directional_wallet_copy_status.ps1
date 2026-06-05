$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Write-Host "=== ETH directional copy process ==="
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*eth_directional_wallet_copy_sim.py*" } | Select-Object ProcessId, CommandLine
Write-Host "`n=== Recent console ==="
Get-Content (Join-Path $workdir "eth_directional_copy_console.log") -Tail 20 -ErrorAction SilentlyContinue
Write-Host "`n=== Recent errors ==="
Get-Content (Join-Path $workdir "eth_directional_copy_error.log") -Tail 20 -ErrorAction SilentlyContinue
Write-Host "`n=== Recent simulated trades ==="
$trades = Join-Path $workdir "eth_directional_wallet_copy_sim.csv"
if (Test-Path $trades) {
  Import-Csv $trades | Select-Object -Last 10 | Format-Table -AutoSize
} else {
  Write-Host "No ETH simulated trades yet."
}
