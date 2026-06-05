$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*bnb_directional_wallet_copy_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "BNB directional wallet copy simulator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

Push-Location -LiteralPath $workdir
python .\crypto_directional_wallet_discovery.py --once --asset-name BNB --keyword bnb --query "BNB above" --query "BNB between" --query "BNB price" --high-min-trades 20 --small-min-trades 5 --output .\bnb_directional_wallet_candidates.csv

$argsList = @(
  "-u", ".\bnb_directional_wallet_copy_sim.py",
  "--asset-name", "BNB",
  "--asset-keyword", "bnb",
  "--strategy-key", "bnb_directional_copy",
  "--wallet-candidates", ".\bnb_directional_wallet_candidates.csv",
  "--candidate-limit", "12",
  "--candidate-recommendation", "OBSERVE_HIGH",
  "--candidate-recommendation", "KEEP_OBSERVING",
  "--min-candidate-score", "50",
  "--min-candidate-trades", "5",
  "--reload-wallets-each-scan",
  "--stake-usdc", "10",
  "--bankroll-usdc", "1000",
  "--interval", "12",
  "--live-only",
  "--min-price", "0.05",
  "--max-price", "0.99",
  "--yes-max-price", "0.99",
  "--max-slippage-bps", "650",
  "--max-source-to-ask-gap", "0.050",
  "--max-source-age-sec", "180",
  "--min-source-usdc", "1",
  "--min-ask-depth-usdc", "10",
  "--max-market-stake-usdc", "20",
  "--max-wallet-market-entries", "2",
  "--max-open-positions", "100",
  "--max-hours-to-end", "120",
  "--log", ".\bnb_directional_wallet_copy_sim.csv",
  "--audit-log", ".\bnb_directional_trade_audit.csv",
  "--reject-log", ".\bnb_directional_rejects.csv",
  "--seen", ".\bnb_directional_seen.json",
  "--alert-file", ".\latest_bnb_directional_copy_alert.txt"
)
Start-Process -FilePath "pythonw.exe" -ArgumentList $argsList -WorkingDirectory $workdir -WindowStyle Hidden
Pop-Location

Write-Host "BNB directional wallet copy simulator started in hidden background."
