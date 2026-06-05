$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "ai_signal_console.log"
$stderr = Join-Path $workdir "ai_signal_error.log"

Set-Location $workdir
$env:PYTHONUTF8 = "1"
$env:AI_DECISION_MODE = "local"

python .\start_ai_signal_background.py
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
Write-Host "Mode: simulation only, BTC 15m observation"
