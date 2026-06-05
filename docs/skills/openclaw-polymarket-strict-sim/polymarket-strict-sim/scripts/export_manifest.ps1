$ErrorActionPreference = "Stop"

$skillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$projectRoot = Split-Path -Parent (Split-Path -Parent $skillDir)
$assetsDir = Join-Path $skillDir "assets"
$manifest = Join-Path $assetsDir "current_data_manifest.csv"

New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null

$includeExtensions = @(".py", ".ps1", ".csv", ".json", ".md", ".html", ".txt", ".log", ".example")
$excludeNames = @(".env")
$excludePatterns = @(
  "\\__pycache__\\",
  "\\openclaw_skill\\polymarket-strict-sim\\assets\\current_data_manifest.csv$"
)

$rows = foreach ($file in Get-ChildItem -Path $projectRoot -File -Recurse) {
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

  $hash = ""
  try {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName -ErrorAction Stop).Hash.ToLowerInvariant()
  } catch {
    $hash = "hash_error"
  }

  [PSCustomObject]@{
    relative_path = $relative
    bytes = $file.Length
    last_write_time = $file.LastWriteTime.ToString("o")
    sha256 = $hash
  }
}

$rows |
  Sort-Object relative_path |
  Export-Csv -Path $manifest -NoTypeInformation -Encoding UTF8

Write-Host "Manifest written: $manifest"
Write-Host "Rows: $($rows.Count)"

