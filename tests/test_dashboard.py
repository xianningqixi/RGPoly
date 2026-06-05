from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.dashboard import render_html
from rgpoly.store import Store


class DashboardTests(unittest.TestCase):
    def test_dashboard_renders_entry_points(self) -> None:
        db_path = Path(".runtime/test_dashboard.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        store = Store(db_path)
        try:
            html = render_html(store, config_path=Path("config/rgpoly.toml"), execution_mode="dry_run")
            self.assertIn("RGPoly 控制台", html)
            self.assertIn("操作入口", html)
            self.assertIn("待执行订单", html)
            self.assertIn("run --dry-run", html)
            self.assertIn("run --live --execute-limit 1", html)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
