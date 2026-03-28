"""Tests for spyhop report command: DB helpers, formatting functions, integration."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from spyhop.cli import _compute_mtm, _format_pnl, _format_time_to_close
from spyhop.storage import db


# ── Shared test helpers ──────────────────────────────────────────


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db._SCHEMA)
    db._migrate(conn)
    return conn


def _insert_dummy_trade(conn: sqlite3.Connection, **kw) -> int:
    trade = {
        "timestamp": "2026-03-10T12:00:00+00:00",
        "wallet": "0xabc123",
        "side": "BUY",
        "usdc_size": 15000.0,
        "price": 0.50,
        "condition_id": "cond_001",
        "asset_id": "asset_001",
        "market_question": "Will X happen?",
        "tx_hash": "0xtx001",
        "outcome": "Yes",
        "outcome_index": 0,
    }
    trade.update(kw)
    return db.insert_trade(conn, trade)


def _insert_dummy_signal(conn: sqlite3.Connection, trade_id: int, score: float = 8.0, thesis: str = "insider") -> int:
    sig = {
        "trade_id": trade_id,
        "timestamp": "2026-03-10T12:00:00+00:00",
        "composite_score": score,
        "fresh_mult": 2.0,
        "fresh_detail": "1 prior trades",
        "size_mult": 3.0,
        "size_detail": "large",
        "niche_mult": 2.0,
        "niche_detail": "niche",
        "is_alert": 1,
        "is_critical": 0,
        "thesis": thesis,
    }
    return db.insert_signal(conn, sig)


def _insert_position(conn: sqlite3.Connection, trade_id: int, signal_id: int, **kw) -> int:
    pos = {
        "trade_id": trade_id,
        "signal_id": signal_id,
        "condition_id": "cond_001",
        "market_question": "Will X happen?",
        "outcome": "Yes",
        "outcome_index": 0,
        "side": "BUY",
        "entry_price": 0.50,
        "size_usd": 5000.0,
        "token_qty": 10000.0,
        "score_at_entry": 8.0,
        "wallet": "0xabc123",
        "entry_timestamp": "2026-03-10T12:00:00+00:00",
        "thesis": "insider",
    }
    pos.update(kw)
    return db.insert_paper_position(conn, pos)


def _close(conn: sqlite3.Connection, pos_id: int, exit_price: float, pnl: float) -> None:
    db.close_position(conn, pos_id, exit_price, "2026-03-11T12:00:00+00:00", pnl)


def _upsert_market(conn: sqlite3.Connection, condition_id: str, end_date: str | None = None,
                   outcome_prices: str = '["0.60", "0.40"]') -> None:
    db.upsert_market(conn, {
        "condition_id": condition_id,
        "question": "Test market",
        "slug": "test-market",
        "volume": 50000.0,
        "volume_24hr": 15000.0,
        "outcome_prices": outcome_prices,
        "end_date": end_date,
        "last_fetched": "2026-03-10T12:00:00+00:00",
    })


# ── TestGetResolvedPositions ─────────────────────────────────────


class TestGetResolvedPositions:
    def test_empty(self):
        conn = _make_conn()
        assert db.get_resolved_positions(conn) == []

    def test_excludes_open_positions(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        _insert_position(conn, tid, sid)  # OPEN, not closed
        assert db.get_resolved_positions(conn) == []

    def test_returns_resolved(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        pos_id = _insert_position(conn, tid, sid)
        _close(conn, pos_id, 1.0, 5000.0)
        rows = db.get_resolved_positions(conn)
        assert len(rows) == 1
        assert rows[0]["status"] == "RESOLVED"

    def test_ordered_exit_timestamp_desc(self):
        conn = _make_conn()
        for i in range(3):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_{i:03d}")
            sid = _insert_dummy_signal(conn, tid)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_{i:03d}")
            db.close_position(conn, pos_id, 1.0, f"2026-03-{10+i:02d}T12:00:00+00:00", 1000.0)
        rows = db.get_resolved_positions(conn)
        timestamps = [r["exit_timestamp"] for r in rows]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_thesis_filter(self):
        conn = _make_conn()
        for thesis in ("insider", "sporty_investor"):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_{thesis}")
            sid = _insert_dummy_signal(conn, tid, thesis=thesis)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_{thesis}", thesis=thesis)
            _close(conn, pos_id, 1.0, 1000.0)
        rows = db.get_resolved_positions(conn, thesis="sporty_investor")
        assert len(rows) == 1
        assert rows[0]["thesis"] == "sporty_investor"

    def test_realized_pnl_present(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        pos_id = _insert_position(conn, tid, sid)
        _close(conn, pos_id, 1.0, 4999.99)
        rows = db.get_resolved_positions(conn)
        assert abs(rows[0]["realized_pnl"] - 4999.99) < 0.01


# ── TestGetOpenPositionsWithMarket ───────────────────────────────


class TestGetOpenPositionsWithMarket:
    def test_empty(self):
        conn = _make_conn()
        assert db.get_open_positions_with_market(conn) == []

    def test_includes_end_date(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        _insert_position(conn, tid, sid)
        _upsert_market(conn, "cond_001", end_date="2026-04-01")
        rows = db.get_open_positions_with_market(conn)
        assert rows[0]["end_date"] == "2026-04-01"

    def test_null_end_date_when_no_market(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        _insert_position(conn, tid, sid)
        rows = db.get_open_positions_with_market(conn)
        assert rows[0]["end_date"] is None

    def test_sorted_soonest_end_date_first(self):
        conn = _make_conn()
        for i, end_date in enumerate(("2026-04-10", "2026-04-01", "2026-04-20")):
            cid = f"cond_{i:03d}"
            tid = _insert_dummy_trade(conn, condition_id=cid)
            sid = _insert_dummy_signal(conn, tid)
            _insert_position(conn, tid, sid, condition_id=cid)
            _upsert_market(conn, cid, end_date=end_date)
        rows = db.get_open_positions_with_market(conn)
        end_dates = [r["end_date"] for r in rows]
        assert end_dates == sorted(end_dates)

    def test_null_end_date_sorts_last(self):
        conn = _make_conn()
        # Position with known end_date
        tid1 = _insert_dummy_trade(conn, condition_id="cond_001")
        sid1 = _insert_dummy_signal(conn, tid1)
        _insert_position(conn, tid1, sid1, condition_id="cond_001")
        _upsert_market(conn, "cond_001", end_date="2026-04-01")
        # Position with no market row
        tid2 = _insert_dummy_trade(conn, condition_id="cond_002")
        sid2 = _insert_dummy_signal(conn, tid2)
        _insert_position(conn, tid2, sid2, condition_id="cond_002")

        rows = db.get_open_positions_with_market(conn)
        assert rows[0]["condition_id"] == "cond_001"
        assert rows[1]["end_date"] is None

    def test_includes_cached_outcome_prices(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        _insert_position(conn, tid, sid)
        _upsert_market(conn, "cond_001", outcome_prices='["0.72", "0.28"]')
        rows = db.get_open_positions_with_market(conn)
        assert rows[0]["cached_outcome_prices"] == '["0.72", "0.28"]'

    def test_excludes_resolved_positions(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        pos_id = _insert_position(conn, tid, sid)
        _close(conn, pos_id, 1.0, 5000.0)
        assert db.get_open_positions_with_market(conn) == []


# ── TestGetScoreBandBreakdown ─────────────────────────────────────


class TestGetScoreBandBreakdown:
    def test_empty(self):
        conn = _make_conn()
        assert db.get_score_band_breakdown(conn) == []

    def test_single_band_win(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid, score=8.3)
        pos_id = _insert_position(conn, tid, sid, score_at_entry=8.3)
        _close(conn, pos_id, 1.0, 5000.0)
        rows = db.get_score_band_breakdown(conn)
        assert len(rows) == 1
        assert rows[0]["band_floor"] == 8
        assert rows[0]["count"] == 1
        assert rows[0]["wins"] == 1

    def test_loss_not_counted_as_win(self):
        conn = _make_conn()
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid, score=7.5)
        pos_id = _insert_position(conn, tid, sid, score_at_entry=7.5)
        _close(conn, pos_id, 0.0, -5000.0)
        rows = db.get_score_band_breakdown(conn)
        assert rows[0]["wins"] == 0

    def test_multiple_bands(self):
        conn = _make_conn()
        for score in (7.1, 8.5):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_{score}")
            sid = _insert_dummy_signal(conn, tid, score=score)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_{score}", score_at_entry=score)
            _close(conn, pos_id, 1.0, 1000.0)
        rows = db.get_score_band_breakdown(conn)
        band_floors = [r["band_floor"] for r in rows]
        assert 7 in band_floors
        assert 8 in band_floors

    def test_ordered_ascending(self):
        conn = _make_conn()
        for score in (9.0, 5.5, 7.2):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_{score}")
            sid = _insert_dummy_signal(conn, tid, score=score)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_{score}", score_at_entry=score)
            _close(conn, pos_id, 1.0, 1000.0)
        rows = db.get_score_band_breakdown(conn)
        floors = [r["band_floor"] for r in rows]
        assert floors == sorted(floors)

    def test_win_pct_calculation(self):
        conn = _make_conn()
        # 2 wins, 1 loss at score band 8
        for i, pnl in enumerate((5000.0, 5000.0, -5000.0)):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_00{i}")
            sid = _insert_dummy_signal(conn, tid, score=8.5)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_00{i}", score_at_entry=8.5)
            exit_p = 1.0 if pnl > 0 else 0.0
            _close(conn, pos_id, exit_p, pnl)
        rows = db.get_score_band_breakdown(conn)
        assert rows[0]["wins"] == 2
        assert rows[0]["count"] == 3
        # Win pct is computed in Python by caller — just verify raw values here

    def test_thesis_filter(self):
        conn = _make_conn()
        for thesis in ("insider", "sporty_investor"):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_{thesis}")
            sid = _insert_dummy_signal(conn, tid, thesis=thesis)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_{thesis}", thesis=thesis, score_at_entry=7.0)
            _close(conn, pos_id, 1.0, 1000.0)
        rows = db.get_score_band_breakdown(conn, thesis="insider")
        assert len(rows) == 1

    def test_avg_pnl(self):
        conn = _make_conn()
        for i, pnl in enumerate((3000.0, 5000.0)):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_00{i}")
            sid = _insert_dummy_signal(conn, tid, score=8.0)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_00{i}", score_at_entry=8.0)
            _close(conn, pos_id, 1.0, pnl)
        rows = db.get_score_band_breakdown(conn)
        assert abs(rows[0]["avg_pnl"] - 4000.0) < 0.01


# ── TestFormatTimeToClose ─────────────────────────────────────────

NOW = datetime(2026, 3, 27, 12, 0, 0, tzinfo=timezone.utc)


class TestFormatTimeToClose:
    def test_none_input(self):
        result = _format_time_to_close(None, _now=NOW)
        assert result.plain == "—"
        assert "dim" in str(result._spans) or result.style == "dim"

    def test_empty_string(self):
        result = _format_time_to_close("", _now=NOW)
        assert result.plain == "—"

    def test_past_date(self):
        yesterday = "2026-03-26T12:00:00+00:00"
        result = _format_time_to_close(yesterday, _now=NOW)
        assert result.plain == "past"

    def test_hours_only(self):
        future = (NOW + timedelta(hours=3, minutes=30)).isoformat()
        result = _format_time_to_close(future, _now=NOW)
        assert result.plain == "3h"

    def test_days_and_hours(self):
        future = (NOW + timedelta(days=1, hours=12)).isoformat()
        result = _format_time_to_close(future, _now=NOW)
        assert result.plain == "1d 12h"

    def test_minutes_only(self):
        future = (NOW + timedelta(minutes=45)).isoformat()
        result = _format_time_to_close(future, _now=NOW)
        assert result.plain == "45m"

    def test_imminent_is_yellow(self):
        future = (NOW + timedelta(minutes=30)).isoformat()
        result = _format_time_to_close(future, _now=NOW)
        assert result.plain == "30m"
        assert result.style == "yellow"

    def test_non_imminent_has_no_style(self):
        future = (NOW + timedelta(hours=5)).isoformat()
        result = _format_time_to_close(future, _now=NOW)
        assert result.style != "yellow"

    def test_naive_date_string_normalized(self):
        # Gamma API returns bare date strings like "2026-06-30" — must not crash
        result = _format_time_to_close("2026-06-30", _now=NOW)
        # Should return a valid label, not crash or return "?"
        assert result.plain not in ("?", "—")

    def test_invalid_string(self):
        result = _format_time_to_close("not-a-date", _now=NOW)
        assert result.plain == "?"


# ── TestComputeMtm ────────────────────────────────────────────────


def _make_pos(**kw) -> dict:
    base = {"outcome_index": 0, "entry_price": 0.50, "token_qty": 10000.0}
    base.update(kw)
    return base


class TestComputeMtm:
    def test_none_prices(self):
        pnl, display = _compute_mtm(_make_pos(), None)
        assert pnl is None
        assert display == "—"

    def test_win_position(self):
        prices = json.dumps(["0.80", "0.20"])
        pnl, display = _compute_mtm(_make_pos(entry_price=0.50, token_qty=10000.0), prices)
        assert pnl == pytest.approx(3000.0)  # (0.80 - 0.50) * 10000

    def test_loss_position(self):
        prices = json.dumps(["0.30", "0.70"])
        pnl, display = _compute_mtm(_make_pos(entry_price=0.50, token_qty=10000.0), prices)
        assert pnl == pytest.approx(-2000.0)  # (0.30 - 0.50) * 10000

    def test_outcome_index_1(self):
        prices = json.dumps(["0.20", "0.80"])
        pnl, _ = _compute_mtm(_make_pos(outcome_index=1, entry_price=0.50, token_qty=10000.0), prices)
        assert pnl == pytest.approx(3000.0)  # (0.80 - 0.50) * 10000

    def test_outcome_index_out_of_range(self):
        prices = json.dumps(["0.50", "0.50"])
        pnl, display = _compute_mtm(_make_pos(outcome_index=5), prices)
        assert pnl is None
        assert display == "—"

    def test_invalid_json(self):
        pnl, display = _compute_mtm(_make_pos(), "not-json{{{")
        assert pnl is None
        assert display == "—"

    def test_price_display_format(self):
        prices = json.dumps(["0.62", "0.38"])
        _, display = _compute_mtm(_make_pos(), prices)
        assert display == "62.0\u00a2"


# ── TestFormatPnl ─────────────────────────────────────────────────


class TestFormatPnl:
    def test_positive_is_green(self):
        result = _format_pnl(12400.0)
        assert result.plain == "$+12,400"
        assert result.style == "green"

    def test_negative_is_red(self):
        result = _format_pnl(-3200.0)
        assert result.plain == "$-3,200"
        assert result.style == "red"

    def test_zero_is_green(self):
        result = _format_pnl(0.0)
        assert result.style == "green"


# ── TestReportDbIntegration ───────────────────────────────────────


class TestReportDbIntegration:
    def test_full_portfolio_state(self):
        """3 resolved (2W/1L) + 2 open — all four DB functions return coherent data."""
        conn = _make_conn()

        # Resolved positions
        for i, (score, pnl, exit_p) in enumerate(((8.5, 5000.0, 1.0), (7.2, 4000.0, 1.0), (6.5, -3000.0, 0.0))):
            tid = _insert_dummy_trade(conn, condition_id=f"res_{i:03d}")
            sid = _insert_dummy_signal(conn, tid, score=score)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"res_{i:03d}", score_at_entry=score)
            _close(conn, pos_id, exit_p, pnl)

        # Open positions (with market data)
        for i in range(2):
            tid = _insert_dummy_trade(conn, condition_id=f"open_{i:03d}")
            sid = _insert_dummy_signal(conn, tid)
            _insert_position(conn, tid, sid, condition_id=f"open_{i:03d}")
            _upsert_market(conn, f"open_{i:03d}", end_date="2026-04-01", outcome_prices='["0.70", "0.30"]')

        resolved = db.get_resolved_positions(conn)
        open_pos = db.get_open_positions_with_market(conn)
        bands = db.get_score_band_breakdown(conn)

        assert len(resolved) == 3
        assert len(open_pos) == 2
        realized_total = sum(r["realized_pnl"] for r in resolved)
        assert abs(realized_total - 6000.0) < 0.01  # 5000 + 4000 - 3000
        wins = sum(1 for r in resolved if r["realized_pnl"] > 0)
        assert wins == 2
        assert len(bands) >= 2  # bands 6 and 7 and 8

    def test_per_thesis_segregation(self):
        conn = _make_conn()
        for thesis in ("insider", "sporty_investor"):
            tid = _insert_dummy_trade(conn, condition_id=f"cond_{thesis}")
            sid = _insert_dummy_signal(conn, tid, score=7.0, thesis=thesis)
            pos_id = _insert_position(conn, tid, sid, condition_id=f"cond_{thesis}", thesis=thesis, score_at_entry=7.0)
            _close(conn, pos_id, 1.0, 1000.0)

        insider_bands = db.get_score_band_breakdown(conn, thesis="insider")
        sporty_bands = db.get_score_band_breakdown(conn, thesis="sporty_investor")
        assert len(insider_bands) == 1
        assert len(sporty_bands) == 1

    def test_zero_positions(self):
        conn = _make_conn()
        assert db.get_resolved_positions(conn) == []
        assert db.get_open_positions_with_market(conn) == []
        assert db.get_score_band_breakdown(conn) == []
        assert db.get_pnl_summary(conn) == []
