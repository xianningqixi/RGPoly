$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*sol_directional_wallet_copy_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "SOL directional wallet copy simulator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

Push-Location -LiteralPath $workdir
python .\crypto_directional_wallet_discovery.py --once --asset-name SOL --keyword solana --query "solana above" --query "solana between" --query "solana price" --high-min-trades 20 --small-min-trades 5 --output .\sol_directional_wallet_candidates.csv

$argsList = @(
  "-u", ".\sol_directional_wallet_copy_sim.py",
  "--asset-name", "SOL",
  "--asset-keyword", "solana",
  "--strategy-key", "sol_directional_copy",
  "--wallet-candidates", ".\sol_directional_wallet_candidates.csv",
  "--candidate-limit", "12",
  "--candidate-recommendation", "OBSERVE_HIGH",
  "--min-candidate-score", "100",
  "--min-candidate-trades", "20",
  "--reload-wallets-each-scan",
  "--stake-usdc", "10",
  "--bankroll-usdc", "1000",
  "--interval", "12",
  "--live-only",
  "--min-price", "0.10",
  "--max-price", "0.99",
  "--yes-max-price", "0.99",
  "--max-slippage-bps", "400",
  "--max-source-to-ask-gap", "0.025",
  "--max-source-age-sec", "75",
  "--min-source-usdc", "3",
  "--min-ask-depth-usdc", "20",
  "--max-market-stake-usdc", "10",
  "--max-wallet-market-entries", "1",
  "--max-open-positions", "100",
  "--max-hours-to-end", "72",
  "--log", ".\sol_directional_wallet_copy_sim.csv",
  "--audit-log", ".\sol_directional_trade_audit.csv",
  "--reject-log", ".\sol_directional_rejects.csv",
  "--seen", ".\sol_directional_seen.json",
  "--alert-file", ".\latest_sol_directional_copy_alert.txt"
)
Start-Process -FilePath "pythonw.exe" -ArgumentList $argsList -WorkingDirectory $workdir -WindowStyle Hidden
Pop-Location

Write-Host "SOL directional wallet copy simulator started in hidden background."
