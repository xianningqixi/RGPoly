param(
    [string]$Config = "config\rgpoly.toml",
    [int]$MaxLoops = 0,
    [ValidateSet("", "manual", "dry_run", "live")]
    [string]$Mode = "",
    [int]$ExecuteLimit = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Runtime = Join-Path $RepoRoot ".runtime"
$Stdout = Join-Path $Runtime "rgpoly_v2.out.log"
$Stderr = Join-Path $Runtime "rgpoly_v2.err.log"

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

$existing = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*rgpoly*" -and $_.CommandLine -like "* run*" }

if ($existing) {
    Write-Host "RGPoly v2 already running:"
    $existing | Select-Object ProcessId, CommandLine | Format-Table -AutoSize
    exit 0
}

$argsList = @("-u", "-m", "rgpoly", "--config", $Config, "run")
if ($MaxLoops -gt 0) {
    $argsList += @("--max-loops", "$MaxLoops")
}
if ($Mode) {
    $argsList += @("--mode", $Mode)
}
if ($ExecuteLimit -gt 0) {
    $argsList += @("--execute-limit", "$ExecuteLimit")
}

$process = Start-Process `
    -FilePath "python.exe" `
    -ArgumentList $argsList `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput $Stdout `
    -RedirectStandardError $Stderr `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Started RGPoly v2 PID=$($process.Id)"
Write-Host "stdout: $Stdout"
Write-Host "stderr: $Stderr"
