$ErrorActionPreference = "Stop"

Write-Host "Set Polymarket Deposit Wallet execution environment."
Write-Host "This saves values for this Windows user. It does not place orders."
Write-Host ""

$privateKeySecure = Read-Host "Paste PRIVATE_KEY for the signing wallet" -AsSecureString
$apiKey = Read-Host "Paste POLY_API_KEY"
$apiSecretSecure = Read-Host "Paste POLY_API_SECRET" -AsSecureString
$passphraseSecure = Read-Host "Paste POLY_API_PASSPHRASE" -AsSecureString
$proxyAddress = Read-Host "Paste POLY_PROXY_ADDRESS / Deposit Wallet address"
$signatureType = Read-Host "Paste POLY_SIGNATURE_TYPE (Deposit Wallet is 3)"

function Convert-SecureStringToPlainText {
  param([Security.SecureString]$SecureValue)
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

$privateKey = Convert-SecureStringToPlainText $privateKeySecure
$apiSecret = Convert-SecureStringToPlainText $apiSecretSecure
$passphrase = Convert-SecureStringToPlainText $passphraseSecure

[Environment]::SetEnvironmentVariable("PRIVATE_KEY", $privateKey.Trim(), "User")
[Environment]::SetEnvironmentVariable("POLY_API_KEY", $apiKey.Trim(), "User")
[Environment]::SetEnvironmentVariable("POLY_API_SECRET", $apiSecret.Trim(), "User")
[Environment]::SetEnvironmentVariable("POLY_API_PASSPHRASE", $passphrase.Trim(), "User")
[Environment]::SetEnvironmentVariable("POLY_PROXY_ADDRESS", $proxyAddress.Trim(), "User")
[Environment]::SetEnvironmentVariable("POLY_SIGNATURE_TYPE", $signatureType.Trim(), "User")
[Environment]::SetEnvironmentVariable("POLY_STRICT_SIM_EXECUTION", "1", "User")

$env:PRIVATE_KEY = $privateKey.Trim()
$env:POLY_API_KEY = $apiKey.Trim()
$env:POLY_API_SECRET = $apiSecret.Trim()
$env:POLY_API_PASSPHRASE = $passphrase.Trim()
$env:POLY_PROXY_ADDRESS = $proxyAddress.Trim()
$env:POLY_SIGNATURE_TYPE = $signatureType.Trim()
$env:POLY_STRICT_SIM_EXECUTION = "1"

Write-Host ""
Write-Host "Environment saved. Running read-only checks..."
python .\api_key_readiness_check.py
python .\polymarket_deposit_wallet_readiness.py
