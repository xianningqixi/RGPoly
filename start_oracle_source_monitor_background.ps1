$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "oracle_source_console.log"
$stderr = Join-Path $workdir "oracle_source_error.log"

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$workdir'; python -u .\oracle_source_monitor.py --interval 600`"" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Oracle source monitor started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
Write-Host "Output: $(Join-Path $workdir 'oracle_source_map.csv')"
