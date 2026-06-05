$ErrorActionPreference = "Stop"

Write-Host "Polymarket API credential setup for local readiness checks only."
Write-Host "This does not enable live trading and does not change strategy code."
Write-Host ""

$apiKey = Read-Host "Paste POLY_API_KEY"
$apiSecretSecure = Read-Host "Paste POLY_API_SECRET" -AsSecureString
$passphraseSecure = Read-Host "Paste POLY_API_PASSPHRASE" -AsSecureString
$proxyAddress = Read-Host "Paste POLY_PROXY_ADDRESS if you use one, otherwise press Enter"
$signatureType = Read-Host "Paste POLY_SIGNATURE_TYPE if you use one, otherwise press Enter"

function Convert-SecureStringToPlainText {
  param([Security.SecureString]$SecureValue)
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

$apiSecret = Convert-SecureStringToPlainText $apiSecretSecure
$passphrase = Convert-SecureStringToPlainText $passphraseSecure

[Environment]::SetEnvironmentVariable("POLY_API_KEY", $apiKey, "User")
[Environment]::SetEnvironmentVariable("POLY_API_SECRET", $apiSecret, "User")
[Environment]::SetEnvironmentVariable("POLY_API_PASSPHRASE", $passphrase, "User")
[Environment]::SetEnvironmentVariable("POLY_STRICT_SIM_EXECUTION", "1", "User")

if ($proxyAddress.Trim()) {
  [Environment]::SetEnvironmentVariable("POLY_PROXY_ADDRESS", $proxyAddress.Trim(), "User")
}
if ($signatureType.Trim()) {
  [Environment]::SetEnvironmentVariable("POLY_SIGNATURE_TYPE", $signatureType.Trim(), "User")
}

$env:POLY_API_KEY = $apiKey
$env:POLY_API_SECRET = $apiSecret
$env:POLY_API_PASSPHRASE = $passphrase
$env:POLY_STRICT_SIM_EXECUTION = "1"
if ($proxyAddress.Trim()) { $env:POLY_PROXY_ADDRESS = $proxyAddress.Trim() }
if ($signatureType.Trim()) { $env:POLY_SIGNATURE_TYPE = $signatureType.Trim() }

Write-Host ""
Write-Host "API environment variables saved for this Windows user."
Write-Host "Live trading remains disabled. Continue using simulation/preflight reports."
Write-Host ""
python .\api_key_readiness_check.py
