$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*btc_high_win_candidate_observation_copy_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "BTC high-win candidate observation simulator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$stdout = Join-Path $workdir "btc_high_win_candidate_observation_copy_console.log"
$stderr = Join-Path $workdir "btc_high_win_candidate_observation_copy_error.log"

$argsList = @(
  "-u", ".\btc_high_win_candidate_observation_copy_sim.py",
  "--strategy-key", "btc_high_win_candidate_observation_copy",
  "--wallet-candidates", ".\btc_high_win_candidate_wallets.csv",
  "--candidate-limit", "15",
  "--candidate-recommendation", "OBSERVE_HIGH",
  "--candidate-recommendation", "OBSERVE_SMALL",
  "--reload-wallets-each-scan",
  "--stake-usdc", "10",
  "--bankroll-usdc", "1000",
  "--interval", "10",
  "--live-only",
  "--allowed-outcome", "No",
  "--block-market-keyword", "reach",
  "--block-market-keyword", "dip",
  "--asset-name", "BTC",
  "--asset-keyword", "bitcoin",
  "--asset-keyword", "btc",
  "--short-window-keyword", "updown",
  "--min-price", "0.10",
  "--max-price", "0.90",
  "--max-slippage-bps", "350",
  "--max-source-to-ask-gap", "0.030",
  "--max-source-age-sec", "420",
  "--min-source-usdc", "1",
  "--min-ask-depth-usdc", "10",
  "--max-market-stake-usdc", "20",
  "--max-wallet-market-entries", "2",
  "--max-open-positions", "100",
  "--max-hours-to-end", "72",
  "--isolated-portfolio-risk",
  "--log", ".\btc_high_win_candidate_observation_copy_sim.csv",
  "--audit-log", ".\btc_high_win_candidate_observation_trade_audit.csv",
  "--reject-log", ".\btc_high_win_candidate_observation_rejects.csv",
  "--exit-signal-log", ".\btc_high_win_candidate_observation_exit_signals.csv",
  "--hedge-signal-log", ".\btc_high_win_candidate_observation_hedge_exit_signals.csv",
  "--btc-price-history", ".\btc_external_price_history.csv",
  "--seen", ".\btc_high_win_candidate_observation_seen.json",
  "--alert-file", ".\latest_btc_high_win_candidate_observation_copy_alert.txt"
)

Start-Process -FilePath "python.exe" `
  -ArgumentList $argsList `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden

Write-Host "BTC high-win candidate observation simulator started in hidden background."
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
