$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location -LiteralPath $workdir
python .\generate_polymarket_api_key_local.py
