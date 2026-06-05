from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.execution import DryRunExecutor
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


if __name__ == "__main__":
    unittest.main()

