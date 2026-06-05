$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*btc_yes_candidate_observation_copy_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "BTC Yes candidate observation copy simulator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\btc_yes_candidate_observation_copy_sim.py",
  "--strategy-key", "btc_yes_candidate_observation_copy",
  "--watch-wallet", "candidate_justinbeaver=0x86a29f88fcc23ea2b0e01b4e186b043e26c873a8",
  "--watch-wallet", "candidate_0x3205=0x81134ca47528889a0ad55f1fe81f5789c2bf288b",
  "--watch-wallet", "candidate_0xfddf22=0xfdf347c62cc8de86e17951e78fd53bfaac342583",
  "--watch-wallet", "candidate_tomcohen=0x1944a4d0d160475a87846aa0f901d46d27dec05d",
  "--watch-wallet", "candidate_averagerandomman=0x8970b56535153baadee991ca25a178ac085636b5",
  "--watch-wallet", "candidate_binyq1iik=0x0b721724064afe45b40eeb95cf3487f8e6d5dc2e",
  "--watch-wallet", "candidate_xrmls=0x265c10c82fb0fc88bb378bf78c1d382651e4a122",
  "--stake-usdc", "10",
  "--yes-stake-usdc", "10",
  "--bankroll-usdc", "1000",
  "--interval", "10",
  "--live-only",
  "--allowed-outcome", "Yes",
  "--block-market-keyword", "reach",
  "--block-market-keyword", "dip",
  "--asset-name", "BTC",
  "--asset-keyword", "bitcoin",
  "--asset-keyword", "btc",
  "--short-window-keyword", "updown",
  "--min-price", "0.10",
  "--max-price", "0.90",
  "--yes-max-price", "0.90",
  "--max-slippage-bps", "350",
  "--yes-max-slippage-bps", "350",
  "--max-source-to-ask-gap", "0.030",
  "--yes-max-source-to-ask-gap", "0.030",
  "--max-source-age-sec", "180",
  "--min-source-usdc", "1",
  "--min-ask-depth-usdc", "10",
  "--yes-min-ask-depth-usdc", "10",
  "--max-market-stake-usdc", "20",
  "--max-wallet-market-entries", "2",
  "--max-open-positions", "100",
  "--max-hours-to-end", "72",
  "--isolated-portfolio-risk",
  "--log", ".\btc_yes_candidate_observation_copy_sim.csv",
  "--audit-log", ".\btc_yes_candidate_observation_trade_audit.csv",
  "--reject-log", ".\btc_yes_candidate_observation_rejects.csv",
  "--exit-signal-log", ".\btc_yes_candidate_observation_exit_signals.csv",
  "--btc-price-history", ".\btc_external_price_history.csv",
  "--seen", ".\btc_yes_candidate_observation_seen.json",
  "--alert-file", ".\latest_btc_yes_candidate_observation_copy_alert.txt"
)

$stdout = Join-Path $workdir "btc_yes_candidate_observation_copy_console.log"
$stderr = Join-Path $workdir "btc_yes_candidate_observation_copy_error.log"
Start-Process -FilePath "python.exe" -ArgumentList $argsList -WorkingDirectory $workdir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Host "BTC Yes candidate observation copy simulator started in hidden background."
