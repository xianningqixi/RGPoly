from __future__ import annotations

from datetime import datetime, timezone

from .config import ExecutionConfig, WalletCopyConfig
from .models import ActivityTrade, OrderBook, iso_utc
from .store import Store


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


class RiskManager:
    def __init__(self, store: Store, execution: ExecutionConfig):
        self.store = store
        self.execution = execution

    def approve_wallet_copy(
        self,
        config: WalletCopyConfig,
        trade: ActivityTrade,
        book: OrderBook | None,
    ) -> tuple[bool, str]:
        if not config.enabled:
            return False, "strategy_disabled"
        if trade.activity_type != "TRADE":
            return False, "not_trade_activity"
        if trade.side.upper() != "BUY":
            return False, "source_not_buy"
        if trade.outcome not in config.allowed_outcomes:
            return False, "outcome_not_allowed"
        if trade.usdc_size < config.min_source_usdc:
            return False, "source_size_too_small"
        if trade.age_seconds > config.max_signal_age_sec:
            return False, "signal_too_old"
        text = f"{trade.title} {trade.slug}"
        if config.required_title_keywords and not _contains_any(text, config.required_title_keywords):
            return False, "keyword_missing"
        if config.blocked_title_keywords and _contains_any(text, config.blocked_title_keywords):
            return False, "keyword_blocked"
        if not book:
            return False, "orderbook_missing"
        if book.best_ask <= 0:
            return False, "best_ask_missing"
        if book.best_ask > config.max_price:
            return False, "best_ask_above_max_price"
        if self.store.open_intent_count() >= self.execution.max_open_intents:
            return False, "open_intent_limit"

        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = self.store.spent_since(iso_utc(day_start))
        if spent + config.stake_usdc > self.execution.max_daily_usdc:
            return False, "daily_usdc_limit"
        return True, "approved"

