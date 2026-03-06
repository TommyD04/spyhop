"""SQLite schema and query helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    wallet          TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    usdc_size       REAL    NOT NULL,
    price           REAL,
    condition_id    TEXT,
    asset_id        TEXT,
    market_question TEXT,
    tx_hash         TEXT
);

CREATE TABLE IF NOT EXISTS markets (
    condition_id    TEXT PRIMARY KEY,
    question        TEXT,
    slug            TEXT,
    volume          REAL,
    volume_24hr     REAL,
    outcome_prices  TEXT,
    last_fetched    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
"""


def init_db(path: Path) -> sqlite3.Connection:
    """Open (or create) the database and ensure schema exists."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def insert_trade(conn: sqlite3.Connection, trade: dict[str, Any]) -> None:
    """Insert a single trade record."""
    conn.execute(
        """INSERT INTO trades
           (timestamp, wallet, side, usdc_size, price, condition_id, asset_id, market_question, tx_hash)
           VALUES (:timestamp, :wallet, :side, :usdc_size, :price, :condition_id, :asset_id, :market_question, :tx_hash)""",
        trade,
    )
    conn.commit()


def get_recent_trades(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent trades, newest first."""
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_market(conn: sqlite3.Connection, condition_id: str) -> dict[str, Any] | None:
    """Fetch a cached market by condition_id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM markets WHERE condition_id = ?", (condition_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_market(conn: sqlite3.Connection, market: dict[str, Any]) -> None:
    """Insert or replace a market cache entry."""
    conn.execute(
        """INSERT OR REPLACE INTO markets
           (condition_id, question, slug, volume, volume_24hr, outcome_prices, last_fetched)
           VALUES (:condition_id, :question, :slug, :volume, :volume_24hr, :outcome_prices, :last_fetched)""",
        market,
    )
    conn.commit()
