from __future__ import annotations

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import EXECUTION_MODES, load_config, normalize_execution_mode, write_default_config
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
    run_mode = run.add_mutually_exclusive_group()
    run_mode.add_argument("--mode", choices=EXECUTION_MODES, dest="mode_override")
    run_mode.add_argument("--manual", action="store_const", const="manual", dest="mode_override")
    run_mode.add_argument("--dry-run", action="store_const", const="dry_run", dest="mode_override")
    run_mode.add_argument("--live", action="store_const", const="live", dest="mode_override")
    run.add_argument("--execute-limit", type=int, default=0)

    execute = sub.add_parser("execute")
    execute.add_argument("--live", action="store_true")
    execute.add_argument("--limit", type=int, default=100)

    doctor = sub.add_parser("doctor")
    doctor_mode = doctor.add_mutually_exclusive_group()
    doctor_mode.add_argument("--mode", choices=EXECUTION_MODES, dest="mode_override")
    doctor_mode.add_argument("--manual", action="store_const", const="manual", dest="mode_override")
    doctor_mode.add_argument("--dry-run", action="store_const", const="dry_run", dest="mode_override")
    doctor_mode.add_argument("--live", action="store_const", const="live", dest="mode_override")
    doctor.add_argument("--check-client", action="store_true")

    derive = sub.add_parser("derive-api-key")
    derive.add_argument("--format", choices=["text", "powershell"], default="powershell")

    intents = sub.add_parser("intents")
    intents.add_argument("--limit", type=int, default=20)

    sub.add_parser("status")

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--output", type=Path, default=Path(".runtime/rgpoly_dashboard.html"))

    dashboard_server = sub.add_parser("dashboard-server")
    dashboard_server.add_argument("--host", default="127.0.0.1")
    dashboard_server.add_argument("--port", type=int, default=8765)

    export = sub.add_parser("export-csv")
    export.add_argument("--table", choices=["activity", "signals", "intents", "receipts"], required=True)
    export.add_argument("--output", type=Path, required=True)
    return parser


def _resolve_execution_mode(config_mode: str, override: str | None) -> str:
    return normalize_execution_mode(override or config_mode)


def _executor_for_mode(mode: str, store: Store, config: Any) -> DryRunExecutor | LiveClobExecutor | None:
    if mode == "manual":
        return None
    if mode == "dry_run":
        return DryRunExecutor(store)
    if mode == "live":
        return LiveClobExecutor(store, config.execution)
    raise AssertionError(mode)


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


async def _run(config_path: Path, max_loops: int, mode_override: str | None, execute_limit: int) -> int:
    from .engine import Engine
    from .polymarket import PolymarketClient

    config = load_config(config_path)
    store = Store(config.engine.db_path)
    mode = _resolve_execution_mode(config.execution.mode, mode_override)
    executor = _executor_for_mode(mode, store, config)
    limit = execute_limit or config.execution.execute_limit_per_loop
    if isinstance(executor, LiveClobExecutor):
        errors = executor.readiness_errors(require_gate=True, require_api_creds=True)
        if errors:
            for error in errors:
                print(f"live_check_error: {error}")
            store.close()
            return 2

    client = PolymarketClient(timeout_sec=config.engine.http_timeout_sec)
    loops = 0
    try:
        engine = Engine(config, store, client)
        async for stats in engine.run_forever():
            loops += 1
            executed = 0
            if executor:
                try:
                    executed = executor.execute_ready(limit)
                except Exception as exc:
                    print(f"execution_error mode={mode}: {exc}")
                    return 2
            summary = ", ".join(f"{item.strategy}: new={item.new_activity} intents={item.intents}" for item in stats)
            print(f"{summary or 'no strategies'} | mode={mode} executed={executed}")
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
        if isinstance(executor, LiveClobExecutor):
            errors = executor.readiness_errors(require_gate=True, require_api_creds=True)
            if errors:
                for error in errors:
                    print(f"live_check_error: {error}")
                return 2
        count = executor.execute_ready(limit)
        print(f"executed={count} mode={'live' if live else 'dry_run'}")
        return 0
    finally:
        store.close()


def _doctor(config_path: Path, mode_override: str | None, check_client: bool) -> int:
    config = load_config(config_path)
    store = Store(config.engine.db_path)
    ok = True
    try:
        mode = _resolve_execution_mode(config.execution.mode, mode_override)
        print(f"config: ok {config_path}")
        print(f"db: ok {config.engine.db_path}")
        print(f"enabled_strategies: {sum(1 for strategy in config.wallet_copy if strategy.enabled)}")
        print(f"ready_intents: {store.open_intent_count()}")
        print(f"execution_mode: {mode}")
        if mode == "live":
            executor = LiveClobExecutor(store, config.execution)
            errors = executor.readiness_errors(require_gate=True, require_api_creds=True)
            if errors:
                ok = False
                for error in errors:
                    print(f"live: error {error}")
            else:
                print("live: ok env_and_gate")
            if check_client and not errors:
                try:
                    executor._make_client()
                    print("clob_client: ok")
                except Exception as exc:
                    ok = False
                    print(f"clob_client: error {exc}")
        return 0 if ok else 2
    finally:
        store.close()


def _payload_value(payload: dict[str, Any], *names: str) -> Any:
    lowered = {key.lower(): value for key, value in payload.items()}
    for name in names:
        if name in payload and payload[name]:
            return payload[name]
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _derive_api_key(config_path: Path, output_format: str) -> int:
    config = load_config(config_path)
    store = Store(config.engine.db_path)
    try:
        executor = LiveClobExecutor(store, config.execution)
        errors = executor.readiness_errors(require_gate=False, require_api_creds=False)
        if errors:
            for error in errors:
                print(f"derive_error: {error}")
            return 2
        payload = executor.derive_api_key()
        api_key = _payload_value(payload, "api_key", "apiKey", "key")
        api_secret = _payload_value(payload, "api_secret", "apiSecret", "secret")
        api_passphrase = _payload_value(payload, "api_passphrase", "apiPassphrase", "passphrase")
        if output_format == "powershell":
            print(f'$env:POLY_API_KEY="{api_key}"')
            print(f'$env:POLY_API_SECRET="{api_secret}"')
            print(f'$env:POLY_API_PASSPHRASE="{api_passphrase}"')
        else:
            print(f"POLY_API_KEY={api_key}")
            print(f"POLY_API_SECRET={api_secret}")
            print(f"POLY_API_PASSPHRASE={api_passphrase}")
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


def _status(config_path: Path) -> int:
    config = load_config(config_path)
    store = Store(config.engine.db_path)
    try:
        summary = store.summary()
        for key, value in summary.items():
            print(f"{key}: {value}")
        rows = store.strategy_counts()
        if rows:
            print("")
            for row in rows:
                print(
                    f"{row['strategy']}: signals={row['signals']} "
                    f"approved={row['approved'] or 0} rejected={row['rejected'] or 0}"
                )
        return 0
    finally:
        store.close()


def _dashboard(config_path: Path, output: Path) -> int:
    from .dashboard import write_dashboard

    config = load_config(config_path)
    store = Store(config.engine.db_path)
    try:
        write_dashboard(store, output, config_path=config_path, execution_mode=config.execution.mode)
        print(f"wrote {output}")
        return 0
    finally:
        store.close()


def _dashboard_server(config_path: Path, host: str, port: int) -> int:
    from .dashboard import render_html

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/", "/index.html", "/health"}:
                self.send_error(404)
                return
            if self.path == "/health":
                payload = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            config = load_config(config_path)
            store = Store(config.engine.db_path)
            try:
                payload = render_html(
                    store,
                    config_path=config_path,
                    execution_mode=config.execution.mode,
                ).encode("utf-8")
            finally:
                store.close()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    config = load_config(config_path)
    print(f"dashboard: http://{host}:{port}/")
    print(f"config: {config_path}")
    print(f"db: {config.engine.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("dashboard stopped")
    finally:
        server.server_close()
    return 0


def _export_csv(config_path: Path, table: str, output: Path) -> int:
    from .dashboard import export_table

    config = load_config(config_path)
    store = Store(config.engine.db_path)
    try:
        export_table(store, table, output)
        print(f"wrote {output}")
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
        return asyncio.run(_run(args.config, args.max_loops, args.mode_override, args.execute_limit))

    if args.command == "execute":
        return _execute(args.config, args.live, args.limit)

    if args.command == "doctor":
        return _doctor(args.config, args.mode_override, args.check_client)

    if args.command == "derive-api-key":
        return _derive_api_key(args.config, args.format)

    if args.command == "intents":
        return _intents(args.config, args.limit)

    if args.command == "status":
        return _status(args.config)

    if args.command == "dashboard":
        return _dashboard(args.config, args.output)

    if args.command == "dashboard-server":
        return _dashboard_server(args.config, args.host, args.port)

    if args.command == "export-csv":
        return _export_csv(args.config, args.table, args.output)

    raise AssertionError(args.command)
