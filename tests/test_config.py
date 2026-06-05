from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.config import load_config


class ConfigTests(unittest.TestCase):
    def test_example_config_loads_multiple_strategies(self) -> None:
        config = load_config(Path("config/rgpoly.example.toml"))
        names = {strategy.name for strategy in config.wallet_copy}
        self.assertIn("btc_directional_copy", names)
        self.assertIn("smart_crypto_copy", names)
        self.assertIn("weather_wallet_copy", names)
        self.assertGreaterEqual(len(config.wallet_copy), 4)


if __name__ == "__main__":
    unittest.main()

