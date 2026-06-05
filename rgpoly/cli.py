from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import load_config, write_default_config
from .execution import DryRunExecutor, LiveClobExecutor
from .store import Store


DEFAULT_CONFIG = Path("config/rgpoly.toml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rgpoly")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-config")
    init.add_argument("--path", type=Path, default=DEFAULT_CONFIG)

    sub.add_parser("migrate")
    sub.add_parser("poll-once")

    run = sub.add_parser("run")
    run.add_argument("--max-loops", type=int, default=0)

    execute = sub.add_parser("execute")
    execute.add_argument("--live", action="store_true")
    execute.add_argument("--limit", type=int, default=100)

    intents = sub.add_parser("intents")
    intents.add_argument("--limit", type=int, default=20)
    return parser


async def _poll_once(config_path: Path) -> int:
    from .engine import Engine
    from .polymarket import PolymarketClient

    config = load_config(config_path)
    store = Store(config.engine.db_path)
    client = PolymarketClient(timeout_sec=config.engine.http_timeout_sec)
    try:
        engine = Engine(config, store, client)
        stats = await engine.poll_once()
        for item in stats:
            print(
                f"{item.strategy}: fetched={item.fetched} new={item.new_activity} "
                f"approved={item.approved} rejected={item.rejected} intents={item.intents}"
            )
        return 0
    finally:
        await client.close()
        store.close()


async def _run(config_path: Path, max_loops: int) -> int:
    from .engine import Engine
    from .polymarket import PolymarketClient

    config = load_config(config_path)
    store = Store(config.engine.db_path)
    client = PolymarketClient(timeout_sec=config.engine.http_timeout_sec)
    loops = 0
    try:
        engine = Engine(config, store, client)
        async for stats in engine.run_forever():
            loops += 1
            summary = ", ".join(f"{item.strategy}: new={item.new_activity} intents={item.intents}" for item in stats)
            print(summary or "no strategies")
            if max_loops and loops >= max_loops:
                return 0
    finally:
        await client.close()
        store.close()
    return 0


def _execute(config_path: Path, live: bool, limit: int) -> int:
    config = load_config(config_path)
    store = Store(config.engine.db_path)
    try:
        executor = LiveClobExecutor(store, config.execution) if live else DryRunExecutor(store)
        count = executor.execute_ready(limit)
        print(f"executed={count} mode={'live' if live else 'dry_run'}")
        return 0
    finally:
        store.close()


def _intents(config_path: Path, limit: int) -> int:
    config = load_config(config_path)
    store = Store(config.engine.db_path)
    try:
        rows = store.ready_intents(limit)
        for row in rows:
            print(
                f"{row['id']} {row['strategy']} {row['amount_usdc']}U "
                f"{row['outcome']} max={row['max_price']} {row['title'][:80]}"
            )
        print(f"ready={len(rows)}")
        return 0
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init-config":
        write_default_config(args.path)
        print(f"wrote {args.path}")
        return 0

    if args.command == "migrate":
        config = load_config(args.config)
        store = Store(config.engine.db_path)
        store.close()
        print(f"migrated {config.engine.db_path}")
        return 0

    if args.command == "poll-once":
        return asyncio.run(_poll_once(args.config))

    if args.command == "run":
        return asyncio.run(_run(args.config, args.max_loops))

    if args.command == "execute":
        return _execute(args.config, args.live, args.limit)

    if args.command == "intents":
        return _intents(args.config, args.limit)

    raise AssertionError(args.command)
