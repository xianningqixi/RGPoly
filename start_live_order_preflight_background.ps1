$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "live_order_preflight_console.log"
$stderr = Join-Path $workdir "live_order_preflight_error.log"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*live_order_preflight.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "Live order preflight is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\live_order_preflight.py",
  "--interval", "10",
  "--strategy", "btc_no_dominant_candidate_copy",
  "--max-stake-usdc", "10",
  "--min-ask-depth-usdc", "10",
  "--max-slippage-bps", "650",
  "--max-source-to-ask-gap", "0.030",
  "--max-source-age-sec", "420",
  "--btc-price-history", ".\btc_external_price_history.csv",
  "--output", ".\live_order_intents.csv"
)

$process = Start-Process `
  -FilePath "pythonw.exe" `
  -ArgumentList $argsList `
  -WorkingDirectory $workdir `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -PassThru

$process.Id | Set-Content -Path (Join-Path $workdir "live_order_preflight.pid") -Encoding ASCII

Write-Host "Live order preflight started in hidden background mode."
Write-Host "PID: $($process.Id)"
Write-Host "Output: $(Join-Path $workdir 'live_order_intents.csv')"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
