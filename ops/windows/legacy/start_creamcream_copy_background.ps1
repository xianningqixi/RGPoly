$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$stdout = Join-Path $workdir "creamcream_copy_console.log"
$stderr = Join-Path $workdir "creamcream_copy_error.log"

Write-Host "CreamCream copy simulator is PAUSED."
Write-Host "Reason: finalized audit shows negative realized ROI and very high historical slippage."
Write-Host "CreamCream watcher can keep observing, but no new copy-sim entries will be opened."
exit 0

$process = Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$workdir'; python -u .\creamcream_copy_sim.py --stake-usdc 10 --interval 20 --max-source-age-sec 10 --max-slippage-bps 150 --max-source-to-ask-gap 0.01 --min-ask-depth-usdc 30 --max-market-stake-usdc 10 --max-market-entries 1 --min-cluster-buys 4 --min-cluster-usdc 50 --max-sell-ratio 0.20`"" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "CreamCream copy simulator started in background."
Write-Host "Launcher PID: $($process.Id)"
Write-Host "Console log: $stdout"
Write-Host "Error log: $stderr"
