<#
.SYNOPSIS
  Start the wallet-copy executor in dry-run or live mode.

.DESCRIPTION
  Polls the trade audit CSV and places FOK orders on Polymarket CLOB
  for OPEN trades matching the specified strategy.

.PARAMETER Strategy
  Which strategy to execute: btc_directional, weather_high_prob, 
  or btc_directional_live_shadow.

.PARAMETER Execute
  Switch to enable real order placement. Requires:
    $env:POLY_WALLET_COPY_ENABLED = "I_UNDERSTAND_REAL_MONEY_RISK"

.PARAMETER MaxUsdc
  Max USDC per trade (default: strategy-defined).

.PARAMETER Once
  Single pass, then exit (default: continuous polling).

.EXAMPLES
  # Dry-run BTC directional
  .\start_wallet_copy_executor.ps1 -Strategy btc_directional

  # Single-pass dry-run weather
  .\start_wallet_copy_executor.ps1 -Strategy weather_high_prob -Once

  # Live with 5 USDC max per trade (set env first!)
  $env:POLY_WALLET_COPY_ENABLED = "I_UNDERSTAND_REAL_MONEY_RISK"
  .\start_wallet_copy_executor.ps1 -Strategy btc_directional -Execute -MaxUsdc 5 -Once
#>

param(
    [Parameter(Mandatory)]
    [ValidateSet("btc_directional","weather_high_prob","btc_directional_live_shadow")]
    [string]$Strategy,

    [switch]$Execute,
    [double]$MaxUsdc = 0,
    [switch]$Once,
    [int]$Interval = 60
)

$scriptPath = Split-Path -Parent $PSCommandPath
$python = "python"

$args = @(
    "$scriptPath\wallet_copy_executor.py"
    "--strategy", $Strategy
)

if ($Execute) {
    if ($env:POLY_WALLET_COPY_ENABLED -ne "I_UNDERSTAND_REAL_MONEY_RISK") {
        Write-Warning "POLY_WALLET_COPY_ENABLED not set to I_UNDERSTAND_REAL_MONEY_RISK"
        Write-Warning "Falling back to dry-run mode"
    }
    $args += "--execute"
}

if ($MaxUsdc -gt 0) {
    $args += "--max-usdc"
    $args += [string]$MaxUsdc
}

if ($Once) {
    $args += "--once"
}

$args += "--interval"
$args += [string]$Interval

Write-Host "=== Wallet Copy Executor ===" -ForegroundColor Cyan
Write-Host "Strategy: $Strategy"
Write-Host "Mode: $(&{if ($Execute -and $env:POLY_WALLET_COPY_ENABLED -eq 'I_UNDERSTAND_REAL_MONEY_RISK') {'LIVE'} else {'DRY-RUN'}})"
Write-Host "Max per trade: $(if ($MaxUsdc -gt 0) {"$MaxUsdc USDC"} else {'strategy default'})"
Write-Host "Mode: $(if ($Once) {'single pass'} else {'continuous polling'})"
Write-Host ""

& $python $args
