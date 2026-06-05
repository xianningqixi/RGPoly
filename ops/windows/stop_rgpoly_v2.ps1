$ErrorActionPreference = "Stop"

$processes = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*rgpoly*" -and $_.CommandLine -like "* run*" }

if (-not $processes) {
    Write-Host "RGPoly v2 is not running."
    exit 0
}

foreach ($process in $processes) {
    Write-Host "Stopping RGPoly v2 PID=$($process.ProcessId)"
    Stop-Process -Id $process.ProcessId -Force
}

