from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.config import ExecutionConfig, WalletCopyConfig
from rgpoly.models import ActivityTrade, OrderBook
from rgpoly.risk import RiskManager
from rgpoly.store import Store


class RiskTests(unittest.TestCase):
    def test_rejects_expensive_orderbook(self) -> None:
        db_path = Path(".runtime/test_risk.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        store = Store(db_path)
        try:
            risk = RiskManager(store, ExecutionConfig())
            config = WalletCopyConfig(
                name="test",
                wallets={"alice": "0xabc"},
                max_price=0.5,
                min_source_usdc=1,
                required_title_keywords=("bitcoin",),
            )
            trade = ActivityTrade.from_api(
                "alice",
                "0xabc",
                {
                    "type": "TRADE",
                    "side": "BUY",
                    "outcome": "Yes",
                    "price": 0.4,
                    "size": 10,
                    "usdcSize": 4,
                    "title": "Bitcoin above 100k",
                    "slug": "bitcoin-above-100k",
                    "asset": "123",
                    "transactionHash": "0xtx",
                    "timestamp": None,
                },
            )
            ok, reason = risk.approve_wallet_copy(
                config,
                trade,
                OrderBook("123", best_bid=0.59, best_ask=0.6, ask_depth_usdc=100, bid_depth_usdc=100),
            )
            self.assertFalse(ok)
            self.assertEqual(reason, "best_ask_above_max_price")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
