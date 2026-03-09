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
    tx_hash         TEXT,
    outcome         TEXT,
    outcome_index   INTEGER
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

CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id),
    timestamp       TEXT    NOT NULL,
    composite_score REAL    NOT NULL,
    fresh_mult      REAL    NOT NULL DEFAULT 1.0,
    fresh_detail    TEXT,
    size_mult       REAL    NOT NULL DEFAULT 1.0,
    size_detail     TEXT,
    niche_mult      REAL    NOT NULL DEFAULT 1.0,
    niche_detail    TEXT,
    is_alert        INTEGER NOT NULL DEFAULT 0,
    is_critical     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    event_slug      TEXT PRIMARY KEY,
    title           TEXT,
    tags            TEXT,
    primary_tag     TEXT,
    last_fetched    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
CREATE INDEX IF NOT EXISTS idx_wallets_trade_count ON wallets(trade_count);
CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_trade ON signals(trade_id);

CREATE TABLE IF NOT EXISTS paper_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id),
    signal_id       INTEGER NOT NULL REFERENCES signals(id),
    condition_id    TEXT    NOT NULL,
    market_question TEXT,
    outcome         TEXT    NOT NULL,
    outcome_index   INTEGER NOT NULL DEFAULT 0,
    side            TEXT    NOT NULL DEFAULT 'BUY',
    entry_price     REAL    NOT NULL,
    size_usd        REAL    NOT NULL,
    token_qty       REAL    NOT NULL,
    score_at_entry  REAL    NOT NULL,
    wallet          TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'OPEN',
    entry_timestamp TEXT    NOT NULL,
    exit_price      REAL,
    exit_timestamp  TEXT,
    realized_pnl    REAL
);

CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_positions(status);
CREATE INDEX IF NOT EXISTS idx_paper_condition ON paper_positions(condition_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns to existing tables that predate V3."""
    for col, typ in [("outcome", "TEXT"), ("outcome_index", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def init_db(path: Path) -> sqlite3.Connection:
    """Open (or create) the database and ensure schema exists."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def insert_trade(conn: sqlite3.Connection, trade: dict[str, Any]) -> int:
    """Insert a single trade record. Returns the row ID."""
    cur = conn.execute(
        """INSERT INTO trades
           (timestamp, wallet, side, usdc_size, price, condition_id, asset_id,
            market_question, tx_hash, outcome, outcome_index)
           VALUES (:timestamp, :wallet, :side, :usdc_size, :price, :condition_id,
                   :asset_id, :market_question, :tx_hash, :outcome, :outcome_index)""",
        trade,
    )
    conn.commit()
    return cur.lastrowid


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


def insert_signal(conn: sqlite3.Connection, signal: dict[str, Any]) -> int:
    """Insert a detection signal. Returns the row ID."""
    cur = conn.execute(
        """INSERT INTO signals
           (trade_id, timestamp, composite_score,
            fresh_mult, fresh_detail, size_mult, size_detail,
            niche_mult, niche_detail, is_alert, is_critical)
           VALUES (:trade_id, :timestamp, :composite_score,
                   :fresh_mult, :fresh_detail, :size_mult, :size_detail,
                   :niche_mult, :niche_detail, :is_alert, :is_critical)""",
        signal,
    )
    conn.commit()
    return cur.lastrowid


def get_event(conn: sqlite3.Connection, event_slug: str) -> dict[str, Any] | None:
    """Fetch a cached event by slug, or None if not found."""
    row = conn.execute(
        "SELECT * FROM events WHERE event_slug = ?", (event_slug,)
    ).fetchone()
    return dict(row) if row else None


def upsert_event(conn: sqlite3.Connection, event: dict[str, Any]) -> None:
    """Insert or replace an event cache entry."""
    conn.execute(
        """INSERT OR REPLACE INTO events
           (event_slug, title, tags, primary_tag, last_fetched)
           VALUES (:event_slug, :title, :tags, :primary_tag, :last_fetched)""",
        event,
    )
    conn.commit()


def get_recent_signals(
    conn: sqlite3.Connection, limit: int = 50, min_score: float = 0.0
) -> list[dict[str, Any]]:
    """Return recent signals joined with trade data, sorted by score descending."""
    rows = conn.execute(
        """SELECT s.*, t.wallet, t.side, t.usdc_size, t.price,
                  t.market_question, t.condition_id
           FROM signals s
           JOIN trades t ON s.trade_id = t.id
           WHERE s.composite_score >= ?
           ORDER BY s.composite_score DESC
           LIMIT ?""",
        (min_score, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Paper position helpers ──────────────────────────────────────────


def insert_paper_position(conn: sqlite3.Connection, position: dict[str, Any]) -> int:
    """Insert a paper position. Returns the row ID."""
    cur = conn.execute(
        """INSERT INTO paper_positions
           (trade_id, signal_id, condition_id, market_question, outcome,
            outcome_index, side, entry_price, size_usd, token_qty,
            score_at_entry, wallet, entry_timestamp)
           VALUES (:trade_id, :signal_id, :condition_id, :market_question, :outcome,
                   :outcome_index, :side, :entry_price, :size_usd, :token_qty,
                   :score_at_entry, :wallet, :entry_timestamp)""",
        position,
    )
    conn.commit()
    return cur.lastrowid


def get_open_positions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all open paper positions."""
    rows = conn.execute(
        "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def count_open_positions(conn: sqlite3.Connection) -> int:
    """Return count of open paper positions."""
    row = conn.execute(
        "SELECT COUNT(*) FROM paper_positions WHERE status = 'OPEN'"
    ).fetchone()
    return row[0]


def sum_deployed_capital(conn: sqlite3.Connection) -> float:
    """Return total USD deployed in open paper positions."""
    row = conn.execute(
        "SELECT COALESCE(SUM(size_usd), 0.0) FROM paper_positions WHERE status = 'OPEN'"
    ).fetchone()
    return row[0]


def has_position_on(conn: sqlite3.Connection, condition_id: str, outcome: str) -> bool:
    """Check if there's already an open position on this condition+outcome."""
    row = conn.execute(
        """SELECT 1 FROM paper_positions
           WHERE condition_id = ? AND outcome = ? AND status = 'OPEN'
           LIMIT 1""",
        (condition_id, outcome),
    ).fetchone()
    return row is not None


def delete_all_paper_positions(conn: sqlite3.Connection) -> int:
    """Delete all paper positions. Returns count deleted."""
    cur = conn.execute("DELETE FROM paper_positions")
    conn.commit()
    return cur.rowcount
