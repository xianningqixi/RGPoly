from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat()


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def stable_id(*parts: Any, prefix: str = "") -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}{digest}" if prefix else digest


class DecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class IntentStatus(StrEnum):
    READY = "READY"
    DRY_RUN_FILLED = "DRY_RUN_FILLED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ActivityTrade:
    wallet_alias: str
    wallet_address: str
    activity_type: str
    side: str
    outcome: str
    price: float
    size: float
    usdc_size: float
    title: str
    slug: str
    event_slug: str
    asset: str
    tx_hash: str
    source_ts: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return stable_id(
            self.wallet_address.lower(),
            self.tx_hash,
            self.asset,
            self.side,
            self.outcome,
            self.size,
            self.price,
            prefix="act_",
        )

    @property
    def age_seconds(self) -> float:
        if not self.source_ts:
            return 0.0
        return max(0.0, (utc_now() - self.source_ts.astimezone(timezone.utc)).total_seconds())

    @classmethod
    def from_api(cls, wallet_alias: str, wallet_address: str, row: dict[str, Any]) -> "ActivityTrade":
        return cls(
            wallet_alias=wallet_alias,
            wallet_address=wallet_address.lower(),
            activity_type=str(row.get("type") or ""),
            side=str(row.get("side") or ""),
            outcome=str(row.get("outcome") or ""),
            price=fnum(row.get("price")),
            size=fnum(row.get("size")),
            usdc_size=fnum(row.get("usdcSize")),
            title=str(row.get("title") or ""),
            slug=str(row.get("slug") or ""),
            event_slug=str(row.get("eventSlug") or ""),
            asset=str(row.get("asset") or row.get("tokenId") or ""),
            tx_hash=str(row.get("transactionHash") or row.get("tx") or ""),
            source_ts=parse_time(row.get("timestamp")),
            raw=dict(row),
        )


@dataclass(frozen=True)
class MarketToken:
    token_id: str
    outcome: str
    tick_size: str = "0.01"
    neg_risk: bool = False


@dataclass(frozen=True)
class OrderBook:
    token_id: str
    best_bid: float
    best_ask: float
    ask_depth_usdc: float
    bid_depth_usdc: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyDecision:
    id: str
    strategy: str
    status: DecisionStatus
    reason: str
    activity_key: str
    wallet_alias: str
    wallet_address: str
    token_id: str
    outcome: str
    side: str
    stake_usdc: float
    max_price: float
    source_price: float
    best_ask: float
    title: str
    slug: str
    created_at: str = field(default_factory=iso_utc)

    def as_json(self) -> str:
        payload = asdict(self)
        payload["status"] = str(self.status)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class OrderIntent:
    id: str
    signal_id: str
    strategy: str
    token_id: str
    side: str
    outcome: str
    amount_usdc: float
    max_price: float
    title: str
    slug: str
    tick_size: str = "0.01"
    neg_risk: bool = False
    status: IntentStatus = IntentStatus.READY
    created_at: str = field(default_factory=iso_utc)


@dataclass(frozen=True)
class ExecutionReceipt:
    id: str
    intent_id: str
    status: IntentStatus
    order_id: str = ""
    fill_price: float = 0.0
    shares: float = 0.0
    spent_usdc: float = 0.0
    fee_usdc: float = 0.0
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=iso_utc)
