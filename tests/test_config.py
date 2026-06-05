from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.config import load_config, write_config


class ConfigTests(unittest.TestCase):
    def test_example_config_loads_multiple_strategies(self) -> None:
        config = load_config(Path("config/rgpoly.example.toml"))
        names = {strategy.name for strategy in config.wallet_copy}
        self.assertIn("btc_directional_copy", names)
        self.assertIn("smart_crypto_copy", names)
        self.assertIn("weather_wallet_copy", names)
        self.assertGreaterEqual(len(config.wallet_copy), 4)
        self.assertEqual(config.execution.mode, "dry_run")
        self.assertEqual(config.execution.order_type, "FOK")

    def test_config_writes_and_loads_roundtrip(self) -> None:
        source = load_config(Path("config/rgpoly.example.toml"))
        target = Path(".runtime/test_rgpoly_config.toml")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        write_config(target, source)
        loaded = load_config(target)
        self.assertEqual(loaded.engine.poll_interval_ms, source.engine.poll_interval_ms)
        self.assertEqual(loaded.execution.mode, source.execution.mode)
        self.assertEqual(len(loaded.wallet_copy), len(source.wallet_copy))
        self.assertEqual(loaded.wallet_copy[0].wallets, source.wallet_copy[0].wallets)


if __name__ == "__main__":
    unittest.main()
