# install_polymarket_worker_task.ps1 - Install Windows Scheduled Task for BTC copy worker.
# Run as Administrator. The daemon also requires POLY_BTC_COPY_WORKER_ENABLED
# to be set to I_UNDERSTAND_REAL_MONEY_RISK before it will place orders.

$taskName = "PolymarketBTCCopyWorker"
$pythonw = "C:\Users\Administrator\AppData\Local\Python\bin\pythonw.exe"
$script = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket\polymarket_btc_copy_worker_daemon.py"
$workDir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
$user = "Administrator"

# Remove existing task if any
schtasks /Delete /TN $taskName /F 2>$null

# Create task: run on user logon, hidden, restart on failure
schtasks /Create /TN $taskName /TR "$pythonw $script" /SC ONLOGON `
    /RU $user /IT /F `
    /RL HIGHEST /DELAY 0000:30 `
    /DU 9999:59 /K 1>$null

# Set restart on failure (3 retries, 1 min apart)
schtasks /Change /TN $taskName /Z 1>$null

# Start it now
schtasks /Run /TN $taskName 2>$null

Write-Output "Task '$taskName' installed and started."
