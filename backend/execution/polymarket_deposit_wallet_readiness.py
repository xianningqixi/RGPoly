#!/usr/bin/env python3
"""Read-only Polymarket deposit-wallet readiness check.

This script never places orders. It verifies that the configured API creds,
signature type, funder/proxy address, and CLOB balance/allowance are internally
consistent enough for a separate executor to attempt orders.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any


USDC_POS = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
POLYGON_RPC_URLS = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.llamarpc.com",
    "https://polygon-rpc.com",
]


def win_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or "")
    except Exception:
        return ""


def env(name: str) -> str:
    return os.environ.get(name) or win_user_env(name)


def mask(value: str) -> str:
    value = str(value or "")
    if not value:
        return "<missing>"
    if len(value) <= 14:
        return value
    return f"{value[:8]}...{value[-6:]}"


def rpc_call(method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    last_error: Exception | None = None
    for url in POLYGON_RPC_URLS:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "polymarket-readiness/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())
            if "error" in data:
                raise RuntimeError(data["error"])
            return data.get("result")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(last_error or "all polygon rpc endpoints failed")


def erc20_balance(token: str, address: str) -> float:
    if not address:
        return 0.0
    data = "0x70a08231" + address.lower().replace("0x", "").rjust(64, "0")
    result = rpc_call("eth_call", [{"to": token, "data": data}, "latest"])
    return int(result or "0x0", 16) / 1_000_000


def matic_balance(address: str) -> float:
    if not address:
        return 0.0
    result = rpc_call("eth_getBalance", [address, "latest"])
    return int(result or "0x0", 16) / 1e18


def signer_address(private_key: str) -> str:
    if not private_key:
        return ""
    try:
        from eth_account import Account
    except Exception:
        return ""
    key = private_key if private_key.startswith("0x") else "0x" + private_key
    try:
        return Account.from_key(key).address
    except Exception:
        return ""


@dataclass
class CheckResult:
    item: str
    status: str
    detail: str


def clob_checks() -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        from py_clob_client_v2 import ApiCreds, BalanceAllowanceParams, ClobClient
    except Exception as exc:
        return [CheckResult("py_clob_client_v2", "ERROR", f"import failed: {exc}")]

    key = env("PRIVATE_KEY")
    api_key = env("POLY_API_KEY")
    api_secret = env("POLY_API_SECRET")
    passphrase = env("POLY_API_PASSPHRASE")
    funder = env("POLY_PROXY_ADDRESS")
    sig_text = env("POLY_SIGNATURE_TYPE")
    sig_type = int(sig_text) if sig_text else None

    if not all([key, api_key, api_secret, passphrase]):
        return [CheckResult("clob_client", "MISSING", "PRIVATE_KEY/API credentials are incomplete")]

    try:
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=passphrase)
        client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            key=key,
            creds=creds,
            signature_type=sig_type,
            funder=funder or None,
        )
        out.append(CheckResult("clob_client_init", "OK", f"signature_type={sig_text or '<none>'} funder={mask(funder)}"))
    except Exception as exc:
        return [CheckResult("clob_client_init", "ERROR", str(exc)[:300])]

    for asset_type in ("COLLATERAL", "USDC"):
        try:
            value = client.get_balance_allowance(BalanceAllowanceParams(asset_type=asset_type))
            out.append(CheckResult(f"clob_balance_allowance_{asset_type}", "OK", json.dumps(value, default=str)[:500]))
        except Exception as exc:
            out.append(CheckResult(f"clob_balance_allowance_{asset_type}", "ERROR", str(exc)[:300]))
    return out


def main() -> int:
    private_key = env("PRIVATE_KEY")
    proxy = env("POLY_PROXY_ADDRESS")
    sig = env("POLY_SIGNATURE_TYPE")
    signer = signer_address(private_key)

    print("# Polymarket Deposit Wallet Readiness")
    print("")
    print("Read-only. No orders are placed. Secrets are not printed.")
    print("")
    print(f"- signer/private-key wallet: {mask(signer)}")
    print(f"- POLY_PROXY_ADDRESS/funder: {mask(proxy)}")
    print(f"- POLY_SIGNATURE_TYPE: {sig or '<missing>'}")

    if signer and proxy and signer.lower() != proxy.lower():
        print("- wallet_relation: signer and funder are different; this is normal only for Deposit Wallet/proxy flow")
    elif signer and proxy:
        print("- wallet_relation: signer and funder are the same")
    else:
        print("- wallet_relation: incomplete")

    for label, address in (("signer", signer), ("funder", proxy)):
        if not address:
            continue
        try:
            print(f"- {label} Polygon USDC native: {erc20_balance(USDC_POS, address):.4f}")
            print(f"- {label} Polygon USDC.e: {erc20_balance(USDC_E, address):.4f}")
            print(f"- {label} MATIC: {matic_balance(address):.6f}")
        except Exception as exc:
            print(f"- {label} on-chain balance check error: {str(exc)[:200]}")

    print("")
    print("| item | status | detail |")
    print("|---|---|---|")
    for row in clob_checks():
        safe_detail = row.detail.replace("|", "/")
        print(f"| {row.item} | {row.status} | {safe_detail} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
