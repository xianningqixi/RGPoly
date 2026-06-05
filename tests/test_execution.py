from __future__ import annotations

import unittest
from os import environ
from pathlib import Path

from rgpoly.config import ExecutionConfig
from rgpoly.execution import DryRunExecutor
from rgpoly.execution import LiveClobExecutor
from rgpoly.models import OrderIntent, stable_id
from rgpoly.store import Store


class ExecutionTests(unittest.TestCase):
    def test_dry_run_executor_marks_ready_intents(self) -> None:
        db_path = Path(".runtime/test_execution.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        store = Store(db_path)
        try:
            intent = OrderIntent(
                id=stable_id("intent", "one", prefix="ord_"),
                signal_id="sig_one",
                strategy="test",
                token_id="123",
                side="BUY",
                outcome="Yes",
                amount_usdc=10,
                max_price=0.5,
                title="Bitcoin above 100k",
                slug="bitcoin-above-100k",
            )
            self.assertTrue(store.create_intent(intent))
            self.assertEqual(DryRunExecutor(store).execute_ready(), 1)
            self.assertEqual(store.open_intent_count(), 0)
        finally:
            store.close()

    def test_live_executor_refuses_without_ack_and_credentials(self) -> None:
        db_path = Path(".runtime/test_execution_live.sqlite")
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        store = Store(db_path)
        try:
            for name in (
                "RGPOLY_LIVE_ENABLED",
                "PRIVATE_KEY",
                "POLY_API_KEY",
                "POLY_API_SECRET",
                "POLY_API_PASSPHRASE",
            ):
                environ.pop(name, None)
            errors = LiveClobExecutor(store, ExecutionConfig()).readiness_errors()
            self.assertTrue(any("RGPOLY_LIVE_ENABLED" in error for error in errors))
            self.assertTrue(any("PRIVATE_KEY" in error for error in errors))
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
