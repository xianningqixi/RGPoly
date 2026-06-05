$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$out = Join-Path $workdir "bond_style_console.log"
$err = Join-Path $workdir "bond_style_error.log"

$env:PYTHONIOENCODING = "utf-8"

Start-Process -FilePath $python `
  -ArgumentList "-u", ".\bond_style_market_scanner.py", "--sample-size", "600", "--interval", "60", "--stake-usdc", "10", "--max-hours-to-end", "72", "--min-price", "0.75", "--max-price", "0.985", "--max-spread", "0.05", "--min-ask-depth-usdc", "50" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err `
  -WindowStyle Hidden

Write-Host "Bond-style market scanner started in background."
Write-Host "Console log: $out"
Write-Host "Error log: $err"
Write-Host "Candidates: $(Join-Path $workdir 'bond_style_candidates.csv')"
