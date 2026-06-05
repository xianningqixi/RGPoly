from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .config import ExecutionConfig
from .models import ExecutionReceipt, IntentStatus, fnum, stable_id
from .store import Store


CLOB_URL = "https://clob.polymarket.com"
REQUIRED_LIVE_ENV = {
    "PRIVATE_KEY": ("PRIVATE_KEY", "POLY_PRIVATE_KEY", "PK"),
    "POLY_API_KEY": ("POLY_API_KEY", "CLOB_API_KEY"),
    "POLY_API_SECRET": ("POLY_API_SECRET", "CLOB_SECRET"),
    "POLY_API_PASSPHRASE": ("POLY_API_PASSPHRASE", "CLOB_PASS_PHRASE"),
}


@dataclass(frozen=True)
class LiveEnv:
    private_key: str
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    signature_type: int = 3
    funder: str = ""


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
        self._client: Any | None = None

    def live_enabled(self) -> bool:
        return os.environ.get(self.config.live_enabled_env) == self.config.ack_value

    def missing_required_env(self) -> list[str]:
        return [
            canonical
            for canonical, aliases in REQUIRED_LIVE_ENV.items()
            if not self._env(*aliases)
        ]

    def readiness_errors(self, require_gate: bool = True, require_api_creds: bool = True) -> list[str]:
        errors: list[str] = []
        if require_gate and not self.live_enabled():
            errors.append(f"Set {self.config.live_enabled_env}={self.config.ack_value}")
        required = REQUIRED_LIVE_ENV if require_api_creds else {"PRIVATE_KEY": REQUIRED_LIVE_ENV["PRIVATE_KEY"]}
        for canonical, aliases in required.items():
            if not self._env(*aliases):
                errors.append(f"Missing {canonical} (accepted aliases: {', '.join(aliases)})")
        try:
            import py_clob_client_v2  # noqa: F401
        except ImportError as exc:
            errors.append(f"Missing py-clob-client-v2 package: {exc}")
        return errors

    def execute_ready(self, limit: int = 10) -> int:
        rows = self.store.ready_intents(limit)
        if not rows:
            return 0
        errors = self.readiness_errors(require_gate=True, require_api_creds=True)
        if errors:
            raise RuntimeError(
                "Live execution refused. " + "; ".join(errors)
            )
        client = self._cached_client()
        count = 0
        for row in rows:
            receipt = self._execute_one(client, row)
            if self.store.insert_receipt(receipt):
                count += 1
        return count

    def _env(self, *names: str) -> str:
        for key in names:
            value = os.environ.get(key, "")
            if value:
                return value
        return ""

    def _read_env(self, require_api_creds: bool = True) -> LiveEnv:
        private_key = self._env("PRIVATE_KEY", "POLY_PRIVATE_KEY", "PK")
        api_key = self._env("POLY_API_KEY", "CLOB_API_KEY")
        api_secret = self._env("POLY_API_SECRET", "CLOB_SECRET")
        api_passphrase = self._env("POLY_API_PASSPHRASE", "CLOB_PASS_PHRASE")
        if not private_key:
            raise RuntimeError("Missing PRIVATE_KEY")
        if require_api_creds and (not api_key or not api_secret or not api_passphrase):
            raise RuntimeError("Missing POLY_API_KEY/POLY_API_SECRET/POLY_API_PASSPHRASE")
        signature_type = int(self._env("POLY_SIGNATURE_TYPE") or "3")
        funder = self._env("POLY_PROXY_ADDRESS", "POLY_FUNDER_ADDRESS", "DEPOSIT_WALLET_ADDRESS")
        return LiveEnv(
            private_key=private_key,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            signature_type=signature_type,
            funder=funder,
        )

    def _make_client(self, require_api_creds: bool = True) -> Any:
        from py_clob_client_v2 import ApiCreds, ClobClient

        env = self._read_env(require_api_creds=require_api_creds)
        kwargs: dict[str, Any] = {
            "host": CLOB_URL,
            "chain_id": 137,
            "key": env.private_key,
            "signature_type": env.signature_type,
            "funder": env.funder,
        }
        if require_api_creds:
            kwargs["creds"] = ApiCreds(
                api_key=env.api_key,
                api_secret=env.api_secret,
                api_passphrase=env.api_passphrase,
            )
        return ClobClient(**kwargs)

    def _cached_client(self) -> Any:
        if self._client is None:
            self._client = self._make_client()
        return self._client

    def derive_api_key(self) -> dict[str, Any]:
        client = self._make_client(require_api_creds=False)
        for method_name in ("create_or_derive_api_key", "create_or_derive_api_creds", "create_api_key"):
            method = getattr(client, method_name, None)
            if method:
                result = method()
                return response_payload(result)
        raise RuntimeError("py-clob-client-v2 does not expose an API-key creation method")

    def _execute_one(self, client: Any, row: Any) -> ExecutionReceipt:
        from py_clob_client_v2 import MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side

        intent_id = str(row["id"])
        try:
            sdk_order_type = getattr(OrderType, self.config.order_type)
            order_args = self._market_order_args(
                MarketOrderArgs=MarketOrderArgs,
                token_id=str(row["token_id"]),
                amount=float(row["amount_usdc"]),
                max_price=float(row["max_price"]),
                side=Side.BUY,
                order_type=sdk_order_type,
            )
            options = self._order_options(
                PartialCreateOrderOptions,
                tick_size=str(row["tick_size"] or self.config.tick_size),
                neg_risk=bool(row["neg_risk"]) if row["neg_risk"] is not None else self.config.default_neg_risk,
            )
            response = client.create_and_post_market_order(
                order_args=order_args,
                options=options,
                order_type=sdk_order_type,
            )
            payload = response_payload(response)
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

    def _market_order_args(
        self,
        MarketOrderArgs: Any,
        token_id: str,
        amount: float,
        max_price: float,
        side: Any,
        order_type: Any,
    ) -> Any:
        kwargs = {
            "token_id": token_id,
            "amount": amount,
            "side": side,
            "order_type": order_type,
        }
        try:
            return MarketOrderArgs(price=max_price, **kwargs)
        except TypeError:
            return MarketOrderArgs(**kwargs)

    def _order_options(self, PartialCreateOrderOptions: Any, tick_size: str, neg_risk: bool) -> Any:
        try:
            return PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)
        except TypeError:
            return PartialCreateOrderOptions(tick_size=tick_size)


def response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
        if isinstance(payload, dict):
            return payload
    if hasattr(response, "__dict__"):
        return dict(response.__dict__)
    return {"raw": str(response)}


def receipt_from_error(intent_id: str, error: str, raw: dict[str, Any] | None = None) -> ExecutionReceipt:
    return ExecutionReceipt(
        id=stable_id("receipt", intent_id, error, prefix="rec_"),
        intent_id=intent_id,
        status=IntentStatus.FAILED,
        error=error,
        raw=raw or {},
    )
