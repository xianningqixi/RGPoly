$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "btc_directional_live_shadow_console.log"
$stderr = Join-Path $workdir "btc_directional_live_shadow_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*btc_directional_live_shadow_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "BTC directional live shadow validator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\btc_directional_live_shadow_sim.py",
  "--strategy-key", "btc_directional_live_shadow",
  "--stake-usdc", "30",
  "--bankroll-usdc", "900",
  "--interval", "10",
  "--live-only",
  "--isolated-portfolio-risk",
  "--min-price", "0.10",
  "--max-price", "0.99",
  "--yes-max-price", "0.99",
  "--max-slippage-bps", "500",
  "--max-source-to-ask-gap", "0.035",
  "--max-source-age-sec", "60",
  "--min-source-usdc", "3",
  "--min-ask-depth-usdc", "30",
  "--max-market-stake-usdc", "30",
  "--max-wallet-market-entries", "1",
  "--max-open-positions", "30",
  "--max-hours-to-end", "72",
  "--log", ".\btc_directional_live_shadow_sim.csv",
  "--audit-log", ".\btc_directional_live_shadow_trade_audit.csv",
  "--reject-log", ".\btc_directional_live_shadow_rejects.csv",
  "--seen", ".\btc_directional_live_shadow_mirror_seen.json",
  "--alert-file", ".\latest_btc_directional_live_shadow_alert.txt"
)

Start-Process `
  -FilePath "pythonw.exe" `
  -ArgumentList $argsList `
  -WorkingDirectory $workdir `
  -WindowStyle Hidden

Write-Host "BTC directional live shadow validator started in background."
Write-Host "Process command contains: btc_directional_live_shadow_sim.py"
Write-Host "Trade log: $(Join-Path $workdir 'btc_directional_live_shadow_trade_audit.csv')"
Write-Host "Reject log: $(Join-Path $workdir 'btc_directional_live_shadow_rejects.csv')"
