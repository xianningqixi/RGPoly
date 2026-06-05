from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.dashboard import render_html
from rgpoly.store import Store


class DashboardTests(unittest.TestCase):
    def test_dashboard_renders_empty_store(self) -> None:
        db_path = Path(".runtime/test_dashboard.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        store = Store(db_path)
        try:
            html = render_html(store)
            self.assertIn("RGPoly v2 Dashboard", html)
            self.assertIn("intents_ready", html)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()

