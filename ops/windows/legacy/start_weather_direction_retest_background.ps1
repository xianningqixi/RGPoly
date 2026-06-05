$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "weather_direction_retest_console.log"
$stderr = Join-Path $workdir "weather_direction_retest_error.log"

$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Where-Object { $_.CommandLine -like "*weather_direction_retest_sim.py*" }
if ($existing) {
  $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ", "
  Write-Host "Weather direction retest simulator is already running."
  Write-Host "PID: $pids"
  exit 0
}

$argsList = @(
  "-u", ".\weather_direction_retest_sim.py",
  "--strategy-key", "weather_direction_retest",
  "--live-only",
  "--stake-usdc", "10",
  "--observation-stake-usdc", "10",
  "--bankroll-usdc", "1000",
  "--interval", "5",
  "--activity-limit", "120",
  "--allowed-wallet", "Poligarch",
  "--allowed-wallet", "Railbird",
  "--allowed-outcome", "Yes",
  "--allowed-outcome", "No",
  "--allowed-price-bucket", "0.8-0.9",
  "--allowed-price-bucket", "0.9-1.0",
  "--allowed-wallet-direction", "Poligarch=No:0.9-1.0",
  "--allowed-wallet-direction", "Poligarch=Yes:0.9-1.0",
  "--allowed-wallet-direction", "Railbird=No:0.9-1.0",
  "--wallet-direction-q", "Poligarch=No:0.9-1.0:0.9837",
  "--wallet-direction-q", "Poligarch=Yes:0.9-1.0:1.0000",
  "--wallet-direction-q", "Railbird=No:0.9-1.0:1.0000",
  "--min-direction-edge", "0.005",
  "--min-source-usdc", "1",
  "--min-entry-price", "0.80",
  "--max-entry-price", "0.995",
  "--min-source-price", "0.80",
  "--max-source-price", "0.995",
  "--max-slippage-bps", "350",
  "--max-source-to-ask-gap", "0.035",
  "--max-source-age-sec", "90",
  "--min-ask-depth-usdc", "20",
  "--max-market-stake-usdc", "10",
  "--max-event-stake-usdc", "20",
  "--max-wallet-market-entries", "1",
  "--max-open-positions", "100",
  "--min-realized-pnl-buffer-usdc", "0",
  "--mark-every-scans", "20",
  "--log", ".\weather_direction_retest_sim.csv",
  "--audit-log", ".\weather_direction_retest_trade_audit.csv",
  "--reject-log", ".\weather_direction_retest_rejects.csv",
  "--seen", ".\weather_direction_retest_seen.json",
  "--alert-file", ".\latest_weather_direction_retest_alert.txt"
)

$process = Start-Process `
  -FilePath "python" `
  -ArgumentList $argsList `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Weather direction retest simulator started in background."
Write-Host "PID: $($process.Id)"
Write-Host "Max open positions: 2"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"

