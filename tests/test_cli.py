from __future__ import annotations

import unittest
from pathlib import Path

from rgpoly.cli import _config_from_form
from rgpoly.config import load_config


class CliConfigFormTests(unittest.TestCase):
    def test_config_form_updates_runtime_and_strategy_values(self) -> None:
        current = load_config(Path("config/rgpoly.example.toml"))
        form: dict[str, list[str]] = {
            "strategy_count": [str(len(current.wallet_copy))],
            "engine_db_path": [".runtime/rgpoly.sqlite"],
            "engine_poll_interval_ms": ["900"],
            "engine_activity_limit": ["33"],
            "engine_http_timeout_sec": ["5.5"],
            "execution_mode": ["manual"],
            "execution_execute_limit_per_loop": ["3"],
            "execution_max_daily_usdc": ["12.5"],
            "execution_max_open_intents": ["9"],
            "execution_tick_size": ["0.01"],
            "execution_order_type": ["FOK"],
        }
        for idx, strategy in enumerate(current.wallet_copy):
            prefix = f"strategy_{idx}_"
            form[f"{prefix}name"] = [strategy.name]
            if strategy.enabled:
                form[f"{prefix}enabled"] = ["1"]
            form[f"{prefix}stake_usdc"] = ["7.5" if idx == 0 else str(strategy.stake_usdc)]
            form[f"{prefix}min_entry_price"] = [str(strategy.min_entry_price)]
            form[f"{prefix}max_price"] = [str(strategy.max_price)]
            form[f"{prefix}max_source_to_ask_gap"] = [str(strategy.max_source_to_ask_gap)]
            form[f"{prefix}min_ask_depth_usdc"] = [str(strategy.min_ask_depth_usdc)]
            form[f"{prefix}min_source_usdc"] = [str(strategy.min_source_usdc)]
            form[f"{prefix}max_signal_age_sec"] = [str(strategy.max_signal_age_sec)]
            form[f"{prefix}required_title_keywords"] = [", ".join(strategy.required_title_keywords)]
            form[f"{prefix}blocked_title_keywords"] = [", ".join(strategy.blocked_title_keywords)]
            form[f"{prefix}allowed_outcomes"] = [", ".join(strategy.allowed_outcomes)]
            form[f"{prefix}wallets"] = [
                "\n".join(f"{alias} = {wallet}" for alias, wallet in strategy.wallets.items())
            ]

        updated = _config_from_form(form, current)
        self.assertEqual(updated.execution.mode, "manual")
        self.assertEqual(updated.execution.execute_limit_per_loop, 3)
        self.assertEqual(updated.engine.poll_interval_ms, 900)
        self.assertEqual(updated.wallet_copy[0].stake_usdc, 7.5)
        self.assertEqual(updated.wallet_copy[0].wallets, current.wallet_copy[0].wallets)


if __name__ == "__main__":
    unittest.main()
