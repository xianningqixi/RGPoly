param(
  [Parameter(Mandatory = $true)]
  [string]$TargetDir
)

$ErrorActionPreference = "Stop"

$skillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$projectRoot = Split-Path -Parent (Split-Path -Parent $skillDir)
$targetRoot = [System.IO.Path]::GetFullPath($TargetDir)

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null

$includeExtensions = @(".py", ".ps1", ".csv", ".json", ".md", ".html", ".txt", ".log", ".example")
$excludeNames = @(".env")
$excludePatterns = @("\\__pycache__\\")
$copied = 0
$failed = 0
$errors = @()

foreach ($file in Get-ChildItem -Path $projectRoot -File -Recurse) {
  $relative = $file.FullName.Substring($projectRoot.Length).TrimStart("\")
  $skip = $false
  if ($excludeNames -contains $file.Name) { $skip = $true }
  foreach ($pattern in $excludePatterns) {
    if ($file.FullName -match $pattern) { $skip = $true }
  }
  if ($skip) { continue }

  $ext = $file.Extension
  if ($file.Name -eq ".env.example") { $ext = ".example" }
  if ($includeExtensions -notcontains $ext) { continue }

  $dest = Join-Path $targetRoot $relative
  New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
  try {
    Copy-Item -LiteralPath $file.FullName -Destination $dest -Force -ErrorAction Stop
    $copied += 1
  } catch {
    $failed += 1
    $errors += [PSCustomObject]@{
      relative_path = $relative
      error = $_.Exception.Message
    }
  }
}

if ($errors.Count -gt 0) {
  $errors | Export-Csv -Path (Join-Path $targetRoot "copy_errors.csv") -NoTypeInformation -Encoding UTF8
}

Write-Host "Snapshot target: $targetRoot"
Write-Host "Copied files: $copied"
Write-Host "Failed files: $failed"
if ($failed -gt 0) {
  Write-Host "Failures were written to copy_errors.csv. Stop background scripts and retry for a stable full snapshot."
}
