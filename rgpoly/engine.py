from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .config import AppConfig
from .polymarket import PolymarketClient
from .risk import RiskManager
from .store import Store
from .strategies.wallet_copy import PollStats, WalletCopyStrategy


class Engine:
    def __init__(self, config: AppConfig, store: Store, client: PolymarketClient):
        self.config = config
        self.store = store
        self.client = client
        self.risk = RiskManager(store, config.execution)
        self.strategies = [
            WalletCopyStrategy(strategy, client, store, self.risk, config.engine.activity_limit)
            for strategy in config.wallet_copy
            if strategy.enabled
        ]

    async def poll_once(self) -> list[PollStats]:
        return list(
            await asyncio.gather(
                *[strategy.poll_once() for strategy in self.strategies],
                return_exceptions=False,
            )
        )

    async def run_forever(self) -> AsyncIterator[list[PollStats]]:
        interval = max(0.05, self.config.engine.poll_interval_ms / 1000)
        while True:
            yield await self.poll_once()
            await asyncio.sleep(interval)

