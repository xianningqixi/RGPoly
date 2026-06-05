from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.config import load_config
from rgpoly.dashboard import render_config_html, render_html
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

    def test_config_page_renders_edit_form(self) -> None:
        config = load_config(Path("config/rgpoly.example.toml"))
        html = render_config_html(config, Path("config/rgpoly.toml"))
        self.assertIn("修改 RGPoly 配置", html)
        self.assertIn("保存配置", html)
        self.assertIn("execution_mode", html)
        self.assertIn("strategy_0_wallets", html)


if __name__ == "__main__":
    unittest.main()
