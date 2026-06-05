from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineConfig:
    db_path: Path = Path(".runtime/rgpoly.sqlite")
    poll_interval_ms: int = 750
    activity_limit: int = 20
    http_timeout_sec: float = 4.0
    dry_run: bool = True


@dataclass(frozen=True)
class ExecutionConfig:
    live_enabled_env: str = "RGPOLY_LIVE_ENABLED"
    ack_value: str = "I_UNDERSTAND_REAL_MONEY_RISK"
    max_daily_usdc: float = 50.0
    max_open_intents: int = 25
    tick_size: str = "0.01"


@dataclass(frozen=True)
class WalletCopyConfig:
    name: str
    wallets: dict[str, str]
    enabled: bool = True
    stake_usdc: float = 10.0
    max_price: float = 0.8
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
            dry_run=bool(engine_data.get("dry_run", True)),
        ),
        execution=ExecutionConfig(
            live_enabled_env=str(execution_data.get("live_enabled_env", "RGPOLY_LIVE_ENABLED")),
            ack_value=str(execution_data.get("ack_value", "I_UNDERSTAND_REAL_MONEY_RISK")),
            max_daily_usdc=float(execution_data.get("max_daily_usdc", 50.0)),
            max_open_intents=int(execution_data.get("max_open_intents", 25)),
            tick_size=str(execution_data.get("tick_size", "0.01")),
        ),
        wallet_copy=tuple(strategies),
    )


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).resolve().parents[1] / "config" / "rgpoly.example.toml"
    shutil.copyfile(template, path)
