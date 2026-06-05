from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.models import (
    ActivityTrade,
    DecisionStatus,
    OrderIntent,
    StrategyDecision,
    stable_id,
)
from rgpoly.store import Store


def sample_trade() -> ActivityTrade:
    return ActivityTrade.from_api(
        "alice",
        "0xabc",
        {
            "type": "TRADE",
            "side": "BUY",
            "outcome": "No",
            "price": 0.51,
            "size": 10,
            "usdcSize": 5.1,
            "title": "Bitcoin above 100k",
            "slug": "bitcoin-above-100k",
            "asset": "123",
            "transactionHash": "0xtx",
            "timestamp": 1_700_000_000,
        },
    )


class StoreTests(unittest.TestCase):
    def test_activity_and_intents_are_idempotent(self) -> None:
        db_path = Path(".runtime/test_store.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        store = Store(db_path)
        try:
            trade = sample_trade()
            self.assertTrue(store.insert_activity(trade))
            self.assertFalse(store.insert_activity(trade))

            decision = StrategyDecision(
                id=stable_id("sig", trade.key, prefix="sig_"),
                strategy="test",
                status=DecisionStatus.APPROVED,
                reason="approved",
                activity_key=trade.key,
                wallet_alias=trade.wallet_alias,
                wallet_address=trade.wallet_address,
                token_id="123",
                outcome="No",
                side="BUY",
                stake_usdc=10,
                max_price=0.8,
                source_price=0.51,
                best_ask=0.52,
                title=trade.title,
                slug=trade.slug,
            )
            store.insert_signal(decision)
            intent = OrderIntent(
                id=stable_id("intent", decision.id, prefix="ord_"),
                signal_id=decision.id,
                strategy="test",
                token_id="123",
                side="BUY",
                outcome="No",
                amount_usdc=10,
                max_price=0.8,
                title=trade.title,
                slug=trade.slug,
            )
            self.assertTrue(store.create_intent(intent))
            self.assertFalse(store.create_intent(intent))
            self.assertEqual(store.open_intent_count(), 1)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
