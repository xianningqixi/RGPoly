$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "execution_intent_router_console.log"
$stderr = Join-Path $workdir "execution_intent_router_error.log"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*execution_intent_router.py*" } |
  Select-Object -First 1
if ($existing) {
  Write-Host "Execution intent router is already running."
  Write-Host "PID: $($existing.ProcessId)"
  exit 0
}

$argsList = @(
  "-u", ".\execution_intent_router.py",
  "--interval", "10",
  "--max-intent-age-sec", "300",
  "--allowed-strategy", "btc_no_dominant_candidate_copy",
  "--min-stake-usdc", "9.99",
  "--max-stake-usdc", "10.01"
)

$process = Start-Process `
  -FilePath "pythonw.exe" `
  -ArgumentList $argsList `
  -WorkingDirectory $workdir `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -PassThru

$process.Id | Set-Content -Path (Join-Path $workdir "execution_intent_router.pid") -Encoding ASCII

Write-Host "Execution intent router started in hidden background mode."
Write-Host "PID: $($process.Id)"
Write-Host "Output: $(Join-Path $workdir 'execution_outbox.csv')"
