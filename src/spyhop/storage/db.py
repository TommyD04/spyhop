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

CREATE TABLE IF NOT EXISTS wallets (
    proxy_wallet    TEXT PRIMARY KEY,
    display_name    TEXT,
    pseudonym       TEXT,
    trade_count     INTEGER NOT NULL DEFAULT 0,
    first_trade_ts  TEXT,
    unique_markets  INTEGER NOT NULL DEFAULT 0,
    last_fetched    TEXT NOT NULL,
    profile_depth   TEXT NOT NULL DEFAULT 'shallow'
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
CREATE INDEX IF NOT EXISTS idx_wallets_trade_count ON wallets(trade_count);
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


def get_wallet(conn: sqlite3.Connection, proxy_wallet: str) -> dict[str, Any] | None:
    """Fetch a cached wallet profile, or None if not found."""
    row = conn.execute(
        "SELECT * FROM wallets WHERE proxy_wallet = ?", (proxy_wallet,)
    ).fetchone()
    return dict(row) if row else None


def upsert_wallet(conn: sqlite3.Connection, wallet: dict[str, Any]) -> None:
    """Insert or replace a wallet cache entry."""
    conn.execute(
        """INSERT OR REPLACE INTO wallets
           (proxy_wallet, display_name, pseudonym, trade_count, first_trade_ts,
            unique_markets, last_fetched, profile_depth)
           VALUES (:proxy_wallet, :display_name, :pseudonym, :trade_count, :first_trade_ts,
                   :unique_markets, :last_fetched, :profile_depth)""",
        wallet,
    )
    conn.commit()


def upsert_market(conn: sqlite3.Connection, market: dict[str, Any]) -> None:
    """Insert or replace a market cache entry."""
    conn.execute(
        """INSERT OR REPLACE INTO markets
           (condition_id, question, slug, volume, volume_24hr, outcome_prices, last_fetched)
           VALUES (:condition_id, :question, :slug, :volume, :volume_24hr, :outcome_prices, :last_fetched)""",
        market,
    )
    conn.commit()
