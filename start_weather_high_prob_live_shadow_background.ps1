$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "weather_high_prob_live_shadow_console.log"
$stderr = Join-Path $workdir "weather_high_prob_live_shadow_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*weather_high_prob_live_shadow_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "Weather high-prob live shadow validator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\weather_high_prob_live_shadow_sim.py",
  "--strategy-key", "weather_high_prob_live_shadow",
  "--live-only",
  "--isolated-portfolio-risk",
  "--stake-usdc", "30",
  "--observation-stake-usdc", "30",
  "--bankroll-usdc", "900",
  "--interval", "10",
  "--activity-limit", "100",
  "--allowed-wallet", "Poligarch",
  "--allowed-wallet", "Railbird",
  "--allowed-price-bucket", "0.8-0.9",
  "--allowed-price-bucket", "0.9-1.0",
  "--allowed-wallet-direction", "Poligarch=No:0.9-1.0",
  "--allowed-wallet-direction", "Poligarch=Yes:0.8-0.9",
  "--allowed-wallet-direction", "Poligarch=Yes:0.9-1.0",
  "--allowed-wallet-direction", "Railbird=No:0.9-1.0",
  "--wallet-direction-q", "Poligarch=No:0.9-1.0:0.98373984",
  "--wallet-direction-q", "Poligarch=Yes:0.8-0.9:0.94915254",
  "--wallet-direction-q", "Poligarch=Yes:0.9-1.0:1.0",
  "--wallet-direction-q", "Railbird=No:0.9-1.0:1.0",
  "--min-direction-edge", "0.005",
  "--min-source-usdc", "1",
  "--min-source-price", "0.80",
  "--max-source-price", "0.995",
  "--min-entry-price", "0.80",
  "--max-entry-price", "0.995",
  "--max-slippage-bps", "150",
  "--max-source-to-ask-gap", "0.010",
  "--max-source-age-sec", "60",
  "--min-ask-depth-usdc", "30",
  "--max-market-stake-usdc", "30",
  "--max-event-stake-usdc", "60",
  "--max-wallet-market-entries", "1",
  "--max-open-positions", "30",
  "--mark-every-scans", "30",
  "--log", ".\weather_high_prob_live_shadow_sim.csv",
  "--audit-log", ".\weather_high_prob_live_shadow_trade_audit.csv",
  "--reject-log", ".\weather_high_prob_live_shadow_rejects.csv",
  "--seen", ".\weather_high_prob_live_shadow_mirror_seen.json",
  "--alert-file", ".\latest_weather_high_prob_live_shadow_alert.txt"
)

Start-Process `
  -FilePath "pythonw.exe" `
  -ArgumentList $argsList `
  -WorkingDirectory $workdir `
  -WindowStyle Hidden

Write-Host "Weather high-prob live shadow validator started in background."
Write-Host "Process command contains: weather_high_prob_live_shadow_sim.py"
Write-Host "Trade log: $(Join-Path $workdir 'weather_high_prob_live_shadow_trade_audit.csv')"
Write-Host "Reject log: $(Join-Path $workdir 'weather_high_prob_live_shadow_rejects.csv')"
