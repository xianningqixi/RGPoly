$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*eth_high_quality_directional_copy_sim.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "ETH high-quality directional copy simulator is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\eth_high_quality_directional_copy_sim.py",
  "--strategy-key", "eth_high_quality_directional_copy",
  "--watch-wallet", "candidate_getbipped=0x252d7bae5ec87553dcafb23e275c202ac0d3c456",
  "--watch-wallet", "candidate_pm_maio_2026=0xbd417cdfc83824b2cd31e4428bc1a67c241ba6de",
  "--watch-wallet", "candidate_olegs=0x6e2c3937e6dd094a3a9f814ecbdc289d3fd5b7f8",
  "--watch-wallet", "candidate_gopay=0xb9d2b5b105dc7c0fe651d4015f9627f4007ffb68",
  "--watch-wallet", "candidate_vitaebella=0x561f16deb5653d55d7c9949631101073fabbe4fa",
  "--watch-wallet", "candidate_labistiiia=0x3879b2a3c6f45ab807a8c92835a085e3b472d8c3",
  "--watch-wallet", "candidate_f714=0x84a1099444c9932d86aef2c81d40ab5777082842",
  "--watch-wallet", "candidate_PolymaREKT=0xde242261bcd8d4320113f12230da34d705ca25a8",
  "--watch-wallet", "candidate_fa394a=0xfa394a598dbf573202a8286b45f512c7a383977f",
  "--asset-name", "ETH",
  "--asset-keyword", "ethereum",
  "--asset-keyword", "ether",
  "--stake-usdc", "10",
  "--bankroll-usdc", "1000",
  "--interval", "10",
  "--live-only",
  "--min-price", "0.10",
  "--max-price", "0.99",
  "--yes-max-price", "0.99",
  "--max-slippage-bps", "300",
  "--max-source-to-ask-gap", "0.020",
  "--max-source-age-sec", "75",
  "--min-source-usdc", "3",
  "--min-ask-depth-usdc", "20",
  "--max-market-stake-usdc", "10",
  "--max-wallet-market-entries", "1",
  "--max-open-positions", "100",
  "--max-hours-to-end", "72",
  "--log", ".\eth_high_quality_directional_copy_sim.csv",
  "--audit-log", ".\eth_high_quality_directional_trade_audit.csv",
  "--reject-log", ".\eth_high_quality_directional_rejects.csv",
  "--seen", ".\eth_high_quality_directional_seen.json",
  "--alert-file", ".\latest_eth_high_quality_directional_copy_alert.txt"
)

Start-Process -FilePath "python.exe" -ArgumentList $argsList -WorkingDirectory $workdir -WindowStyle Hidden
Write-Host "ETH high-quality directional copy simulator started in hidden background."
