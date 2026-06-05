from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import WalletCopyConfig
from ..models import (
    ActivityTrade,
    DecisionStatus,
    OrderIntent,
    StrategyDecision,
    stable_id,
)
from ..models import MarketToken, OrderBook
from ..polymarket import PolymarketClient
from ..risk import RiskManager
from ..store import Store


@dataclass(frozen=True)
class PollStats:
    strategy: str
    fetched: int = 0
    new_activity: int = 0
    approved: int = 0
    rejected: int = 0
    intents: int = 0


class WalletCopyStrategy:
    def __init__(
        self,
        config: WalletCopyConfig,
        client: PolymarketClient,
        store: Store,
        risk: RiskManager,
        activity_limit: int,
    ):
        self.config = config
        self.client = client
        self.store = store
        self.risk = risk
        self.activity_limit = activity_limit

    async def poll_once(self) -> PollStats:
        batches = await asyncio.gather(
            *[
                self.client.fetch_activity(alias, wallet, self.activity_limit)
                for alias, wallet in self.config.wallets.items()
            ],
            return_exceptions=True,
        )
        trades: list[ActivityTrade] = []
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            trades.extend(batch)

        fetched = len(trades)
        new_trades = [trade for trade in reversed(trades) if self.store.insert_activity(trade)]
        if not new_trades:
            return PollStats(strategy=self.config.name, fetched=fetched)

        enriched = await self._enrich(new_trades)
        approved = rejected = intents = 0
        for trade in new_trades:
            token, book = enriched.get(trade.key, (None, None))
            token_id = token.token_id if token else ""
            allowed, reason = self.risk.approve_wallet_copy(self.config, trade, book)
            status = DecisionStatus.APPROVED if allowed else DecisionStatus.REJECTED
            decision = StrategyDecision(
                id=stable_id(self.config.name, trade.key, token_id, prefix="sig_"),
                strategy=self.config.name,
                status=status,
                reason=reason,
                activity_key=trade.key,
                wallet_alias=trade.wallet_alias,
                wallet_address=trade.wallet_address,
                token_id=token_id,
                outcome=trade.outcome,
                side="BUY",
                stake_usdc=self.config.stake_usdc,
                max_price=self.config.max_price,
                source_price=trade.price,
                best_ask=book.best_ask if book else 0.0,
                title=trade.title,
                slug=trade.slug,
            )
            self.store.insert_signal(decision)
            if not allowed:
                rejected += 1
                continue
            approved += 1
            intent = OrderIntent(
                id=stable_id("intent", decision.id, prefix="ord_"),
                signal_id=decision.id,
                strategy=self.config.name,
                token_id=token_id,
                side="BUY",
                outcome=trade.outcome,
                amount_usdc=self.config.stake_usdc,
                max_price=self.config.max_price,
                title=trade.title,
                slug=trade.slug,
            )
            if self.store.create_intent(intent):
                intents += 1

        return PollStats(
            strategy=self.config.name,
            fetched=fetched,
            new_activity=len(new_trades),
            approved=approved,
            rejected=rejected,
            intents=intents,
        )

    async def _enrich(
        self,
        trades: list[ActivityTrade],
    ) -> dict[str, tuple[MarketToken | None, OrderBook | None]]:
        token_results = await asyncio.gather(
            *[self.client.token_for_trade(trade) for trade in trades],
            return_exceptions=True,
        )
        token_by_trade: dict[str, MarketToken | None] = {}
        token_ids: set[str] = set()
        for trade, token_result in zip(trades, token_results, strict=True):
            token = None if isinstance(token_result, Exception) else token_result
            token_by_trade[trade.key] = token
            if token and token.token_id:
                token_ids.add(token.token_id)

        unique_token_ids = sorted(token_ids)
        book_results = await asyncio.gather(
            *[self.client.order_book(token_id) for token_id in unique_token_ids],
            return_exceptions=True,
        )
        book_by_token: dict[str, OrderBook | None] = {}
        for token_id, book_result in zip(unique_token_ids, book_results, strict=True):
            book_by_token[token_id] = None if isinstance(book_result, Exception) else book_result

        out: dict[str, tuple[MarketToken | None, OrderBook | None]] = {}
        for trade in trades:
            token = token_by_trade.get(trade.key)
            book = book_by_token.get(token.token_id) if token else None
            out[trade.key] = (token, book)
        return out
