from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import (
    ActivityTrade,
    ExecutionReceipt,
    IntentStatus,
    OrderIntent,
    StrategyDecision,
    iso_utc,
)


SCHEMA_VERSION = 1


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.migrate()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()

    def migrate(self) -> None:
        with self.tx() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity (
                    key TEXT PRIMARY KEY,
                    wallet_alias TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    source_ts TEXT,
                    tx_hash TEXT,
                    slug TEXT,
                    asset TEXT,
                    side TEXT,
                    outcome TEXT,
                    price REAL,
                    usdc_size REAL,
                    seen_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_activity_wallet_seen
                    ON activity(wallet_address, seen_at);
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    activity_key TEXT NOT NULL,
                    wallet_alias TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    token_id TEXT,
                    outcome TEXT,
                    side TEXT,
                    stake_usdc REAL,
                    max_price REAL,
                    source_price REAL,
                    best_ask REAL,
                    title TEXT,
                    slug TEXT,
                    created_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_signals_strategy_created
                    ON signals(strategy, created_at);
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL UNIQUE,
                    strategy TEXT NOT NULL,
                    token_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    amount_usdc REAL NOT NULL,
                    max_price REAL NOT NULL,
                    title TEXT,
                    slug TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_intents_status_created
                    ON intents(status, created_at);
                CREATE TABLE IF NOT EXISTS receipts (
                    id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    order_id TEXT,
                    fill_price REAL,
                    shares REAL,
                    spent_usdc REAL,
                    fee_usdc REAL,
                    error TEXT,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_created
                    ON receipts(created_at);
                """
            )
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def put_kv(self, key: str, value: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO kv(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), iso_utc()),
        )

    def insert_activity(self, trade: ActivityTrade) -> bool:
        with self.tx() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO activity(
                    key, wallet_alias, wallet_address, source_ts, tx_hash, slug, asset,
                    side, outcome, price, usdc_size, seen_at, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.key,
                    trade.wallet_alias,
                    trade.wallet_address,
                    trade.source_ts.isoformat() if trade.source_ts else "",
                    trade.tx_hash,
                    trade.slug,
                    trade.asset,
                    trade.side,
                    trade.outcome,
                    trade.price,
                    trade.usdc_size,
                    iso_utc(),
                    json.dumps(trade.raw, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            return cursor.rowcount > 0

    def insert_signal(self, decision: StrategyDecision) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO signals(
                id, strategy, activity_key, wallet_alias, wallet_address, status, reason,
                token_id, outcome, side, stake_usdc, max_price, source_price, best_ask,
                title, slug, created_at, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                decision.strategy,
                decision.activity_key,
                decision.wallet_alias,
                decision.wallet_address,
                str(decision.status),
                decision.reason,
                decision.token_id,
                decision.outcome,
                decision.side,
                decision.stake_usdc,
                decision.max_price,
                decision.source_price,
                decision.best_ask,
                decision.title,
                decision.slug,
                decision.created_at,
                decision.as_json(),
            ),
        )

    def create_intent(self, intent: OrderIntent) -> bool:
        with self.tx() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO intents(
                    id, signal_id, strategy, token_id, side, outcome, amount_usdc,
                    max_price, title, slug, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.id,
                    intent.signal_id,
                    intent.strategy,
                    intent.token_id,
                    intent.side,
                    intent.outcome,
                    intent.amount_usdc,
                    intent.max_price,
                    intent.title,
                    intent.slug,
                    str(intent.status),
                    intent.created_at,
                    intent.created_at,
                ),
            )
            return cursor.rowcount > 0

    def ready_intents(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT * FROM intents
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (str(IntentStatus.READY), limit),
            )
        )

    def update_intent_status(self, intent_id: str, status: IntentStatus) -> None:
        self.conn.execute(
            "UPDATE intents SET status = ?, updated_at = ? WHERE id = ?",
            (str(status), iso_utc(), intent_id),
        )

    def insert_receipt(self, receipt: ExecutionReceipt) -> bool:
        with self.tx() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO receipts(
                    id, intent_id, status, order_id, fill_price, shares, spent_usdc,
                    fee_usdc, error, raw_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.id,
                    receipt.intent_id,
                    str(receipt.status),
                    receipt.order_id,
                    receipt.fill_price,
                    receipt.shares,
                    receipt.spent_usdc,
                    receipt.fee_usdc,
                    receipt.error,
                    json.dumps(receipt.raw, ensure_ascii=False, separators=(",", ":")),
                    receipt.created_at,
                ),
            )
            if cursor.rowcount:
                conn.execute(
                    "UPDATE intents SET status = ?, updated_at = ? WHERE id = ?",
                    (str(receipt.status), receipt.created_at, receipt.intent_id),
                )
            return cursor.rowcount > 0

    def open_intent_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM intents WHERE status = ?",
            (str(IntentStatus.READY),),
        ).fetchone()
        return int(row["n"] or 0)

    def spent_since(self, iso_cutoff: str) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(spent_usdc), 0) AS total
            FROM receipts
            WHERE created_at >= ? AND status IN (?, ?)
            """,
            (iso_cutoff, str(IntentStatus.EXECUTED), str(IntentStatus.DRY_RUN_FILLED)),
        ).fetchone()
        return float(row["total"] or 0.0)

