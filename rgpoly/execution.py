from __future__ import annotations

import os
from typing import Any

from .config import ExecutionConfig
from .models import ExecutionReceipt, IntentStatus, fnum, stable_id
from .store import Store


CLOB_URL = "https://clob.polymarket.com"


class DryRunExecutor:
    def __init__(self, store: Store):
        self.store = store

    def execute_ready(self, limit: int = 100) -> int:
        count = 0
        for row in self.store.ready_intents(limit):
            receipt = ExecutionReceipt(
                id=stable_id("receipt", row["id"], "dry_run", prefix="rec_"),
                intent_id=row["id"],
                status=IntentStatus.DRY_RUN_FILLED,
                order_id="dry_run",
                fill_price=float(row["max_price"]),
                spent_usdc=float(row["amount_usdc"]),
                raw={key: row[key] for key in row.keys()},
            )
            if self.store.insert_receipt(receipt):
                count += 1
        return count


class LiveClobExecutor:
    def __init__(self, store: Store, config: ExecutionConfig):
        self.store = store
        self.config = config

    def live_enabled(self) -> bool:
        return os.environ.get(self.config.live_enabled_env) == self.config.ack_value

    def execute_ready(self, limit: int = 10) -> int:
        if not self.live_enabled():
            raise RuntimeError(
                f"Live execution refused. Set {self.config.live_enabled_env}="
                f"{self.config.ack_value} to acknowledge real-money risk."
            )
        client = self._make_client()
        count = 0
        for row in self.store.ready_intents(limit):
            receipt = self._execute_one(client, row)
            if self.store.insert_receipt(receipt):
                count += 1
        return count

    def _env(self, name: str, *fallbacks: str) -> str:
        for key in (name, *fallbacks):
            value = os.environ.get(key, "")
            if value:
                return value
        return ""

    def _make_client(self) -> Any:
        from py_clob_client_v2 import ApiCreds, ClobClient

        private_key = self._env("PRIVATE_KEY", "POLY_PRIVATE_KEY", "PK")
        api_key = self._env("POLY_API_KEY", "CLOB_API_KEY")
        api_secret = self._env("POLY_API_SECRET", "CLOB_SECRET")
        api_passphrase = self._env("POLY_API_PASSPHRASE", "CLOB_PASS_PHRASE")
        if not private_key or not api_key or not api_secret or not api_passphrase:
            raise RuntimeError("Missing PRIVATE_KEY/POLY_API_KEY/POLY_API_SECRET/POLY_API_PASSPHRASE")
        signature_type = int(self._env("POLY_SIGNATURE_TYPE") or "3")
        funder = self._env("POLY_PROXY_ADDRESS")
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
        return ClobClient(
            host=CLOB_URL,
            chain_id=137,
            key=private_key,
            creds=creds,
            signature_type=signature_type,
            funder=funder,
        )

    def _execute_one(self, client: Any, row: Any) -> ExecutionReceipt:
        from py_clob_client_v2 import MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side

        intent_id = str(row["id"])
        try:
            response = client.create_and_post_market_order(
                order_args=MarketOrderArgs(
                    token_id=str(row["token_id"]),
                    amount=float(row["amount_usdc"]),
                    side=Side.BUY,
                    order_type=OrderType.FOK,
                ),
                options=PartialCreateOrderOptions(tick_size=self.config.tick_size),
                order_type=OrderType.FOK,
            )
            payload = response if isinstance(response, dict) else {"raw": str(response)}
            success = payload.get("success") is True or str(payload.get("status", "")).lower() in {"matched", "filled"}
            status = IntentStatus.EXECUTED if success else IntentStatus.FAILED
            return ExecutionReceipt(
                id=stable_id("receipt", intent_id, payload.get("orderID") or payload.get("order_id"), prefix="rec_"),
                intent_id=intent_id,
                status=status,
                order_id=str(payload.get("orderID") or payload.get("order_id") or ""),
                fill_price=fnum(payload.get("price") or payload.get("avgPrice")),
                shares=fnum(payload.get("size") or payload.get("filled_size") or payload.get("takingAmount")),
                spent_usdc=fnum(payload.get("amount") or row["amount_usdc"]),
                error="" if success else str(payload.get("errorMsg") or payload.get("error") or payload),
                raw=payload,
            )
        except Exception as exc:
            return receipt_from_error(intent_id, str(exc), {key: row[key] for key in row.keys()})


def receipt_from_error(intent_id: str, error: str, raw: dict[str, Any] | None = None) -> ExecutionReceipt:
    return ExecutionReceipt(
        id=stable_id("receipt", intent_id, error, prefix="rec_"),
        intent_id=intent_id,
        status=IntentStatus.FAILED,
        error=error,
        raw=raw or {},
    )
