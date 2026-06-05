param(
    [string]$Config = "config\rgpoly.toml",
    [ValidateSet("", "manual", "dry_run", "live")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location -LiteralPath $RepoRoot

$processes = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*rgpoly*" }

if ($processes) {
    Write-Host "Processes:"
    $processes | Select-Object ProcessId, CommandLine | Format-Table -AutoSize
} else {
    Write-Host "No RGPoly v2 python process found."
}

Write-Host ""
python -m rgpoly --config $Config status

Write-Host ""
$doctorArgs = @("-m", "rgpoly", "--config", $Config, "doctor")
if ($Mode) {
    $doctorArgs += @("--mode", $Mode)
}
python @doctorArgs
