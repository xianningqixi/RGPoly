from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EXECUTION_MODES = ("manual", "dry_run", "live")
ORDER_TYPES = ("FOK", "FAK")


@dataclass(frozen=True)
class EngineConfig:
    db_path: Path = Path(".runtime/rgpoly.sqlite")
    poll_interval_ms: int = 750
    activity_limit: int = 20
    http_timeout_sec: float = 4.0


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "dry_run"
    execute_limit_per_loop: int = 10
    live_enabled_env: str = "RGPOLY_LIVE_ENABLED"
    ack_value: str = "I_UNDERSTAND_REAL_MONEY_RISK"
    max_daily_usdc: float = 50.0
    max_open_intents: int = 25
    tick_size: str = "0.01"
    default_neg_risk: bool = False
    order_type: str = "FOK"


@dataclass(frozen=True)
class WalletCopyConfig:
    name: str
    wallets: dict[str, str]
    enabled: bool = True
    stake_usdc: float = 10.0
    max_price: float = 0.8
    min_entry_price: float = 0.0
    max_source_to_ask_gap: float = 0.05
    min_ask_depth_usdc: float = 0.0
    min_source_usdc: float = 3.0
    max_signal_age_sec: float = 120.0
    required_title_keywords: tuple[str, ...] = ()
    blocked_title_keywords: tuple[str, ...] = ()
    allowed_outcomes: tuple[str, ...] = ("Yes", "No")


@dataclass(frozen=True)
class AppConfig:
    engine: EngineConfig = field(default_factory=EngineConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    wallet_copy: tuple[WalletCopyConfig, ...] = ()


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return tuple(str(item) for item in value)


def normalize_execution_mode(value: str | None) -> str:
    mode = (value or "dry_run").strip().lower().replace("-", "_")
    if mode not in EXECUTION_MODES:
        raise ValueError(f"execution.mode must be one of {', '.join(EXECUTION_MODES)}")
    return mode


def normalize_order_type(value: str | None) -> str:
    order_type = (value or "FOK").strip().upper()
    if order_type not in ORDER_TYPES:
        raise ValueError(f"execution.order_type must be one of {', '.join(ORDER_TYPES)}")
    return order_type


def load_config(path: Path) -> AppConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    engine_data = data.get("engine") or {}
    execution_data = data.get("execution") or {}
    strategies = []
    for item in data.get("wallet_copy") or []:
        wallets = item.get("wallets") or {}
        strategies.append(
            WalletCopyConfig(
                name=str(item["name"]),
                enabled=bool(item.get("enabled", True)),
                wallets={str(alias): str(wallet).lower() for alias, wallet in wallets.items()},
                stake_usdc=float(item.get("stake_usdc", 10.0)),
                max_price=float(item.get("max_price", 0.8)),
                min_entry_price=float(item.get("min_entry_price", 0.0)),
                max_source_to_ask_gap=float(item.get("max_source_to_ask_gap", 0.05)),
                min_ask_depth_usdc=float(item.get("min_ask_depth_usdc", 0.0)),
                min_source_usdc=float(item.get("min_source_usdc", 3.0)),
                max_signal_age_sec=float(item.get("max_signal_age_sec", 120.0)),
                required_title_keywords=_as_tuple(item.get("required_title_keywords")),
                blocked_title_keywords=_as_tuple(item.get("blocked_title_keywords")),
                allowed_outcomes=_as_tuple(item.get("allowed_outcomes")) or ("Yes", "No"),
            )
        )
    return AppConfig(
        engine=EngineConfig(
            db_path=Path(engine_data.get("db_path", ".runtime/rgpoly.sqlite")),
            poll_interval_ms=int(engine_data.get("poll_interval_ms", 750)),
            activity_limit=int(engine_data.get("activity_limit", 20)),
            http_timeout_sec=float(engine_data.get("http_timeout_sec", 4.0)),
        ),
        execution=ExecutionConfig(
            mode=normalize_execution_mode(execution_data.get("mode")),
            execute_limit_per_loop=int(execution_data.get("execute_limit_per_loop", 10)),
            live_enabled_env=str(execution_data.get("live_enabled_env", "RGPOLY_LIVE_ENABLED")),
            ack_value=str(execution_data.get("ack_value", "I_UNDERSTAND_REAL_MONEY_RISK")),
            max_daily_usdc=float(execution_data.get("max_daily_usdc", 50.0)),
            max_open_intents=int(execution_data.get("max_open_intents", 25)),
            tick_size=str(execution_data.get("tick_size", "0.01")),
            default_neg_risk=bool(execution_data.get("default_neg_risk", False)),
            order_type=normalize_order_type(execution_data.get("order_type")),
        ),
        wallet_copy=tuple(strategies),
    )


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).resolve().parents[1] / "config" / "rgpoly.example.toml"
    shutil.copyfile(template, path)
