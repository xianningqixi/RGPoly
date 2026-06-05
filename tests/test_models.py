from __future__ import annotations

import unittest

from rgpoly.models import ActivityTrade, stable_id


class ModelTests(unittest.TestCase):
    def test_stable_id_is_stable(self) -> None:
        self.assertEqual(stable_id("a", "b"), stable_id("a", "b"))
        self.assertNotEqual(stable_id("a", "b"), stable_id("a", "c"))

    def test_activity_trade_from_api_key(self) -> None:
        row = {
            "type": "TRADE",
            "side": "BUY",
            "outcome": "Yes",
            "price": "0.42",
            "size": "10",
            "usdcSize": "4.2",
            "title": "Bitcoin above 100k",
            "slug": "bitcoin-above-100k",
            "asset": "123",
            "transactionHash": "0xabc",
            "timestamp": 1_700_000_000,
        }
        trade = ActivityTrade.from_api("alice", "0xWallet", row)
        self.assertEqual(trade.wallet_address, "0xwallet")
        self.assertEqual(trade.price, 0.42)
        self.assertTrue(trade.key.startswith("act_"))


if __name__ == "__main__":
    unittest.main()

