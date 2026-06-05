param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Target,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$TargetPath = Join-Path $RepoRoot $Target

if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
    throw "Python target not found: $Target"
}

$moduleDirs = @($RepoRoot)
foreach ($sourceDir in @("backend", "frontend")) {
    $fullSourceDir = Join-Path $RepoRoot $sourceDir
    if (Test-Path -LiteralPath $fullSourceDir) {
        $moduleDirs += Get-ChildItem -LiteralPath $fullSourceDir -Recurse -Filter *.py |
            ForEach-Object { $_.DirectoryName } |
            Sort-Object -Unique
    }
}

$existingPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = ($moduleDirs + $existingPythonPath | Where-Object { $_ }) -join [IO.Path]::PathSeparator
$env:POLY_PROJECT_ROOT = $RepoRoot

Set-Location -LiteralPath $RepoRoot
& python $TargetPath @ScriptArgs
exit $LASTEXITCODE

