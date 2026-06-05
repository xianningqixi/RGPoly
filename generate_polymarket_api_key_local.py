#!/usr/bin/env python3
"""Create or derive Polymarket CLOB API credentials locally.

This script is for local credential generation only. It does not place orders
and does not send credentials anywhere except Polymarket's CLOB API.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from typing import Any

from py_clob_client_v2 import ClobClient


def normalize_private_key(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("private key is empty")
    return text if text.startswith("0x") else f"0x{text}"


def get_private_key(args: argparse.Namespace) -> str:
    env_value = os.getenv(args.private_key_env) or os.getenv("PRIVATE_KEY") or os.getenv("POLY_PRIVATE_KEY")
    if env_value:
        return normalize_private_key(env_value)
    return normalize_private_key(getpass.getpass("请输入你的 Polymarket 钱包私钥，本机输入不会显示: "))


def creds_to_dict(creds: Any) -> dict[str, str]:
    return {
        "apiKey": getattr(creds, "api_key", ""),
        "secret": getattr(creds, "api_secret", ""),
        "passphrase": getattr(creds, "api_passphrase", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Polymarket CLOB API credentials locally.")
    parser.add_argument("--host", default="https://clob.polymarket.com")
    parser.add_argument("--chain-id", type=int, default=137)
    parser.add_argument("--private-key-env", default="POLYMARKET_PRIVATE_KEY")
    parser.add_argument("--nonce", type=int, default=None)
    parser.add_argument("--signature-type", type=int, default=None, help="Optional Polymarket signature_type for proxy wallets.")
    parser.add_argument("--funder", default=None, help="Optional funder address for proxy wallets.")
    parser.add_argument("--readonly", action="store_true", help="Create a readonly API key instead of trading API credentials.")
    parser.add_argument("--output", type=Path, default=None, help="Optional local JSON output file. Default prints only.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    private_key = get_private_key(args)
    client = ClobClient(
        host=args.host,
        chain_id=args.chain_id,
        key=private_key,
        signature_type=args.signature_type,
        funder=args.funder,
    )
    creds = client.create_readonly_api_key() if args.readonly else client.create_or_derive_api_key(nonce=args.nonce)
    payload = creds_to_dict(creds)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"已生成 API 凭证并保存到本机文件: {args.output}")
    else:
        print("已生成 API 凭证。不要发给任何人。")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
