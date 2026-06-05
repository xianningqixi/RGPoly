$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$consoleLog = Join-Path $workdir "ai_signal_console.log"
$errorLog = Join-Path $workdir "ai_signal_error.log"
$decisionsLog = Join-Path $workdir "ai_signal_decisions.csv"
$tradesLog = Join-Path $workdir "ai_signal_trades.csv"
$auditLog = Join-Path $workdir "ai_signal_trade_audit.csv"
$candidateLog = Join-Path $workdir "crypto_lead_lag_candidates.csv"

Write-Host "=== AI signal simulator process ==="
$proc = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Where-Object { $_.CommandLine -like "*ai_signal_simulator.py*" } |
  Select-Object ProcessId, CommandLine
if ($proc) {
  $proc | Format-Table -Wrap
} else {
  Write-Host "No AI signal simulator Python process is running."
}

Write-Host ""
Write-Host "=== Recent console ==="
if (Test-Path $consoleLog) { Get-Content $consoleLog -Encoding UTF8 -Tail 12 } else { Write-Host "No console log yet." }

Write-Host ""
Write-Host "=== Recent errors ==="
if (Test-Path $errorLog) { Get-Content $errorLog -Encoding UTF8 -Tail 12 } else { Write-Host "No error log yet." }

Write-Host ""
Write-Host "=== Recent AI decisions ==="
if (Test-Path $decisionsLog) { Get-Content $decisionsLog -Encoding UTF8 -Tail 10 } else { Write-Host "No AI decisions yet." }

Write-Host ""
Write-Host "=== Recent AI simulated trades ==="
if (Test-Path $tradesLog) { Get-Content $tradesLog -Encoding UTF8 -Tail 10 } else { Write-Host "No AI simulated trades yet." }

Write-Host ""
Write-Host "=== Current lead-lag candidates ==="
if (Test-Path $candidateLog) { Get-Content $candidateLog -Encoding UTF8 -Tail 10 } else { Write-Host "No lead-lag candidates yet." }

Write-Host ""
Write-Host "=== AI audit summary ==="
if (Test-Path $auditLog) {
  $rows = Import-Csv $auditLog
  $final = @($rows | Where-Object { $_.final_result -in @("WIN", "LOSS") -and $_.slippage_final_pnl -ne "" })
  $pnl = ($final | ForEach-Object { [double]$_.slippage_final_pnl } | Measure-Object -Sum).Sum
  $stake = ($final | ForEach-Object { [double]$_.stake } | Measure-Object -Sum).Sum
  $roi = 0
  if ($stake -gt 0) { $roi = $pnl / $stake * 100 }
  Write-Host ("final={0} pnl={1:N4}U roi={2:N2}%" -f $final.Count, $pnl, $roi)
} else {
  Write-Host "No AI audit rows yet."
}
