$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*btc_no_dominant_candidate_copy_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "BTC No-dominant candidate copy simulator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\btc_no_dominant_candidate_copy_sim.py",
  "--strategy-key", "btc_no_dominant_candidate_copy",
  "--watch-wallet", "candidate_justinbeaver=0x86a29f88fcc23ea2b0e01b4e186b043e26c873a8",
  "--watch-wallet", "candidate_0xfddf22=0xfdf347c62cc8de86e17951e78fd53bfaac342583",
  "--watch-wallet", "candidate_tomcohen=0x1944a4d0d160475a87846aa0f901d46d27dec05d",
  "--watch-wallet", "candidate_0x3205=0x81134ca47528889a0ad55f1fe81f5789c2bf288b",
  "--watch-wallet", "candidate_averagerandomman=0x8970b56535153baadee991ca25a178ac085636b5",
  "--watch-wallet", "candidate_binyq1iik=0x0b721724064afe45b40eeb95cf3487f8e6d5dc2e",
  "--watch-wallet", "candidate_xrmls=0x265c10c82fb0fc88bb378bf78c1d382651e4a122",
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
  "--log", ".\btc_no_dominant_candidate_copy_sim.csv",
  "--audit-log", ".\btc_no_dominant_trade_audit.csv",
  "--reject-log", ".\btc_no_dominant_rejects.csv",
  "--exit-signal-log", ".\btc_no_dominant_exit_signals.csv",
  "--hedge-signal-log", ".\btc_no_dominant_hedge_exit_signals.csv",
  "--btc-price-history", ".\btc_external_price_history.csv",
  "--seen", ".\btc_no_dominant_seen.json",
  "--alert-file", ".\latest_btc_no_dominant_candidate_copy_alert.txt"
)

Start-Process -FilePath "python.exe" -ArgumentList $argsList -WorkingDirectory $workdir -WindowStyle Hidden
Write-Host "BTC No-dominant candidate copy simulator started in hidden background."
