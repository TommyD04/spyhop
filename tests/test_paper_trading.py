"""Functional tests for V4 paper trading: risk engine, executor, trader, DB helpers."""

from __future__ import annotations

import sqlite3

from spyhop.config import DEFAULTS, _deep_merge
from spyhop.detector.base import DetectorResult, ScoreResult
from spyhop.paper.executor import PaperEntry, PaperExecutor, PortfolioSummary
from spyhop.paper.risk import RiskDecision, RiskEngine
from spyhop.paper.trader import PaperTrader
from spyhop.storage import db


def _make_config(**overrides) -> dict:
    """Build a config dict with paper section, applying overrides."""
    config = DEFAULTS.copy()
    if overrides:
        config = _deep_merge(config, {"paper": overrides})
    return config


def _make_conn() -> sqlite3.Connection:
    """Create an in-memory DB with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Apply the full schema
    conn.executescript(db._SCHEMA)
    return conn


def _insert_dummy_trade(conn: sqlite3.Connection, **kw) -> int:
    """Insert a minimal trade row, return its ID."""
    trade = {
        "timestamp": "2026-03-08T12:00:00Z",
        "wallet": "0xabc123",
        "side": "BUY",
        "usdc_size": 15000.0,
        "price": 0.62,
        "condition_id": "cond_001",
        "asset_id": "asset_001",
        "market_question": "Will X happen?",
        "tx_hash": "0xtx001",
        "outcome": "Yes",
        "outcome_index": 0,
    }
    trade.update(kw)
    return db.insert_trade(conn, trade)


def _insert_dummy_signal(conn: sqlite3.Connection, trade_id: int, score: float = 8.0) -> int:
    """Insert a minimal signal row, return its ID."""
    sig = {
        "trade_id": trade_id,
        "timestamp": "2026-03-08T12:00:00Z",
        "composite_score": score,
        "fresh_mult": 2.5,
        "fresh_detail": "0 prior trades",
        "size_mult": 1.0,
        "size_detail": "",
        "niche_mult": 2.0,
        "niche_detail": "low volume",
        "is_alert": 1,
        "is_critical": 0,
    }
    return db.insert_signal(conn, sig)


# ── DB Helpers ──────────────────────────────────────────


class TestDBHelpers:
    def test_insert_and_get_positions(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        pos = {
            "trade_id": trade_id,
            "signal_id": signal_id,
            "condition_id": "cond_001",
            "market_question": "Will X happen?",
            "outcome": "Yes",
            "outcome_index": 0,
            "side": "BUY",
            "entry_price": 0.62,
            "size_usd": 5000.0,
            "token_qty": 8064.52,
            "score_at_entry": 8.0,
            "wallet": "0xabc123",
            "entry_timestamp": "2026-03-08T12:00:00Z",
        }
        pos_id = db.insert_paper_position(conn, pos)
        assert pos_id is not None
        assert pos_id > 0

        positions = db.get_open_positions(conn)
        assert len(positions) == 1
        assert positions[0]["condition_id"] == "cond_001"
        assert positions[0]["status"] == "OPEN"

    def test_count_and_sum(self):
        conn = _make_conn()
        assert db.count_open_positions(conn) == 0
        assert db.sum_deployed_capital(conn) == 0.0

        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        for i, size in enumerate([5000, 3000, 7000]):
            db.insert_paper_position(conn, {
                "trade_id": trade_id,
                "signal_id": signal_id,
                "condition_id": f"cond_{i}",
                "market_question": f"Market {i}",
                "outcome": "Yes",
                "outcome_index": 0,
                "side": "BUY",
                "entry_price": 0.5,
                "size_usd": float(size),
                "token_qty": size / 0.5,
                "score_at_entry": 8.0,
                "wallet": "0xabc",
                "entry_timestamp": "2026-03-08T12:00:00Z",
            })

        assert db.count_open_positions(conn) == 3
        assert db.sum_deployed_capital(conn) == 15000.0

    def test_has_position_on(self):
        conn = _make_conn()
        assert not db.has_position_on(conn, "cond_001", "Yes")

        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)
        db.insert_paper_position(conn, {
            "trade_id": trade_id,
            "signal_id": signal_id,
            "condition_id": "cond_001",
            "market_question": "Test",
            "outcome": "Yes",
            "outcome_index": 0,
            "side": "BUY",
            "entry_price": 0.5,
            "size_usd": 5000.0,
            "token_qty": 10000.0,
            "score_at_entry": 8.0,
            "wallet": "0xabc",
            "entry_timestamp": "2026-03-08T12:00:00Z",
        })

        assert db.has_position_on(conn, "cond_001", "Yes")
        assert not db.has_position_on(conn, "cond_001", "No")
        assert not db.has_position_on(conn, "cond_002", "Yes")

    def test_delete_all(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        for i in range(3):
            db.insert_paper_position(conn, {
                "trade_id": trade_id,
                "signal_id": signal_id,
                "condition_id": f"cond_{i}",
                "market_question": "Test",
                "outcome": "Yes",
                "outcome_index": 0,
                "side": "BUY",
                "entry_price": 0.5,
                "size_usd": 1000.0,
                "token_qty": 2000.0,
                "score_at_entry": 8.0,
                "wallet": "0xabc",
                "entry_timestamp": "2026-03-08T12:00:00Z",
            })

        assert db.count_open_positions(conn) == 3
        deleted = db.delete_all_paper_positions(conn)
        assert deleted == 3
        assert db.count_open_positions(conn) == 0


# ── Risk Engine ─────────────────────────────────────────


class TestRiskEngine:
    def _engine(self, conn, **overrides):
        config = _make_config(**overrides)
        return RiskEngine(config, conn)

    def test_basic_allow(self):
        conn = _make_conn()
        engine = self._engine(conn)
        decision = engine.evaluate("cond_001", "Yes", 8.0)
        assert decision.allowed
        # score=8, threshold=7: 5000 * (8/7) = 5714.29
        assert 5700 < decision.position_size_usd < 5750

    def test_score_scaling(self):
        conn = _make_conn()
        engine = self._engine(conn)

        d7 = engine.evaluate("cond_001", "Yes", 7.0)
        d10 = engine.evaluate("cond_002", "Yes", 10.0)

        assert d7.allowed and d10.allowed
        # score=7 → exactly base (5000)
        assert abs(d7.position_size_usd - 5000.0) < 0.01
        # score=10 → 5000 * 10/7 = 7142.86
        assert abs(d10.position_size_usd - 7142.86) < 1.0

    def test_clamp_to_max_position(self):
        conn = _make_conn()
        # max_position_pct=0.05 of 100K = $5K cap, but score=10 wants $7.1K
        engine = self._engine(conn, max_position_pct=0.05)
        decision = engine.evaluate("cond_001", "Yes", 10.0)
        assert decision.allowed
        assert abs(decision.position_size_usd - 5000.0) < 0.01

    def test_reject_duplicate(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)
        db.insert_paper_position(conn, {
            "trade_id": trade_id, "signal_id": signal_id,
            "condition_id": "cond_001", "market_question": "Test",
            "outcome": "Yes", "outcome_index": 0, "side": "BUY",
            "entry_price": 0.5, "size_usd": 5000.0, "token_qty": 10000.0,
            "score_at_entry": 8.0, "wallet": "0xabc",
            "entry_timestamp": "2026-03-08T12:00:00Z",
        })

        engine = self._engine(conn)
        decision = engine.evaluate("cond_001", "Yes", 8.0)
        assert not decision.allowed
        assert "duplicate" in decision.reject_reason

    def test_reject_max_concurrent(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        # Fill up to max_concurrent=3
        for i in range(3):
            db.insert_paper_position(conn, {
                "trade_id": trade_id, "signal_id": signal_id,
                "condition_id": f"cond_{i}", "market_question": "Test",
                "outcome": "Yes", "outcome_index": 0, "side": "BUY",
                "entry_price": 0.5, "size_usd": 1000.0, "token_qty": 2000.0,
                "score_at_entry": 8.0, "wallet": "0xabc",
                "entry_timestamp": "2026-03-08T12:00:00Z",
            })

        engine = self._engine(conn, max_concurrent=3)
        decision = engine.evaluate("cond_new", "Yes", 8.0)
        assert not decision.allowed
        assert "max concurrent" in decision.reject_reason

    def test_exposure_limit(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        # Deploy $45K already (max_exposure_pct=0.50 of 100K = $50K)
        db.insert_paper_position(conn, {
            "trade_id": trade_id, "signal_id": signal_id,
            "condition_id": "cond_big", "market_question": "Test",
            "outcome": "Yes", "outcome_index": 0, "side": "BUY",
            "entry_price": 0.5, "size_usd": 45000.0, "token_qty": 90000.0,
            "score_at_entry": 8.0, "wallet": "0xabc",
            "entry_timestamp": "2026-03-08T12:00:00Z",
        })

        engine = self._engine(conn)
        decision = engine.evaluate("cond_new", "Yes", 7.0)
        assert decision.allowed
        # Only $5K remaining in exposure budget, base size is $5K → clamped to $5K
        assert decision.position_size_usd == 5000.0

    def test_exposure_fully_used(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        db.insert_paper_position(conn, {
            "trade_id": trade_id, "signal_id": signal_id,
            "condition_id": "cond_big", "market_question": "Test",
            "outcome": "Yes", "outcome_index": 0, "side": "BUY",
            "entry_price": 0.5, "size_usd": 50000.0, "token_qty": 100000.0,
            "score_at_entry": 8.0, "wallet": "0xabc",
            "entry_timestamp": "2026-03-08T12:00:00Z",
        })

        engine = self._engine(conn)
        decision = engine.evaluate("cond_new", "Yes", 8.0)
        assert not decision.allowed
        assert "max exposure" in decision.reject_reason


# ── PaperExecutor ───────────────────────────────────────


class TestPaperExecutor:
    def test_execute_and_summary(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        executor = PaperExecutor(conn)
        entry = PaperEntry(
            trade_id=trade_id,
            signal_id=signal_id,
            condition_id="cond_001",
            market_question="Will X happen?",
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            entry_price=0.62,
            size_usd=5000.0,
            token_qty=8064.52,
            score_at_entry=8.0,
            wallet="0xabc123",
            entry_timestamp="2026-03-08T12:00:00Z",
        )
        pos_id = executor.execute(entry)
        assert pos_id > 0

        # Summary without market prices
        summary = executor.get_portfolio_summary(100_000)
        assert summary.starting_capital == 100_000
        assert summary.total_deployed == 5000.0
        assert summary.available_capital == 95_000
        assert summary.open_count == 1
        assert summary.unrealized_pnl == 0.0

    def test_summary_with_market_prices(self):
        conn = _make_conn()
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        executor = PaperExecutor(conn)
        entry = PaperEntry(
            trade_id=trade_id, signal_id=signal_id,
            condition_id="cond_001", market_question="Test",
            outcome="Yes", outcome_index=0, side="BUY",
            entry_price=0.50, size_usd=5000.0, token_qty=10000.0,
            score_at_entry=8.0, wallet="0xabc",
            entry_timestamp="2026-03-08T12:00:00Z",
        )
        executor.execute(entry)

        # Price moved from 0.50 → 0.70: unrealized = (0.70 - 0.50) × 10000 = $2000
        prices = {"cond_001": [0.70, 0.30]}
        summary = executor.get_portfolio_summary(100_000, prices)
        assert abs(summary.unrealized_pnl - 2000.0) < 0.01


# ── PaperTrader (orchestrator) ──────────────────────────


class TestPaperTrader:
    def _make_trade(self, **kw):
        trade = {
            "timestamp": "2026-03-08T12:00:00Z",
            "wallet": "0xabc123",
            "side": "BUY",
            "usdc_size": 15000.0,
            "price": 0.62,
            "condition_id": "cond_001",
            "asset_id": "asset_001",
            "market_question": "Will X happen?",
            "tx_hash": "0xtx001",
            "outcome": "Yes",
            "outcome_index": 0,
        }
        trade.update(kw)
        return trade

    def _make_score(self, composite=8.0) -> ScoreResult:
        return ScoreResult(
            composite=composite,
            signals=[
                DetectorResult("fresh_wallet", 2.5, "0 prior trades"),
                DetectorResult("niche_market", 2.0, "low volume"),
            ],
            alert=composite >= 7,
            critical=composite >= 9,
        )

    def test_below_threshold_returns_none(self):
        conn = _make_conn()
        config = _make_config(enabled=True, min_score=7.0)
        trader = PaperTrader(config, conn)

        trade = self._make_trade()
        score = self._make_score(5.0)
        trade_id = _insert_dummy_trade(conn)

        result = trader.maybe_trade(trade, score, trade_id, None)
        assert result is None

    def test_no_signal_returns_none(self):
        conn = _make_conn()
        config = _make_config(enabled=True)
        trader = PaperTrader(config, conn)

        trade = self._make_trade()
        score = self._make_score(8.0)
        trade_id = _insert_dummy_trade(conn)

        result = trader.maybe_trade(trade, score, trade_id, signal_id=None)
        assert result is None

    def test_buy_creates_position(self):
        conn = _make_conn()
        config = _make_config(enabled=True)
        trader = PaperTrader(config, conn)

        trade = self._make_trade(side="BUY", price=0.62, outcome="Yes", outcome_index=0)
        score = self._make_score(8.0)
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        result = trader.maybe_trade(trade, score, trade_id, signal_id)
        assert result is not None
        assert result.executed
        assert result.position_id > 0
        assert result.size_usd > 0

        # Verify position in DB
        positions = db.get_open_positions(conn)
        assert len(positions) == 1
        assert positions[0]["side"] == "BUY"
        assert positions[0]["outcome"] == "Yes"
        assert positions[0]["outcome_index"] == 0
        assert abs(positions[0]["entry_price"] - 0.62) < 0.001

    def test_sell_normalizes_to_buy_opposite(self):
        """SELL Yes @ 0.62 → BUY No (opposite) @ 0.38"""
        conn = _make_conn()
        config = _make_config(enabled=True)
        trader = PaperTrader(config, conn)

        trade = self._make_trade(side="SELL", price=0.62, outcome="Yes", outcome_index=0)
        score = self._make_score(8.0)
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        result = trader.maybe_trade(trade, score, trade_id, signal_id)
        assert result is not None
        assert result.executed

        positions = db.get_open_positions(conn)
        assert len(positions) == 1
        pos = positions[0]
        assert pos["side"] == "BUY"
        assert pos["outcome_index"] == 1  # flipped from 0 → 1
        assert abs(pos["entry_price"] - 0.38) < 0.001  # 1.0 - 0.62

    def test_sell_no_normalizes_to_buy_yes(self):
        """SELL No @ 0.40 → BUY Yes @ 0.60"""
        conn = _make_conn()
        config = _make_config(enabled=True)
        trader = PaperTrader(config, conn)

        trade = self._make_trade(side="SELL", price=0.40, outcome="No", outcome_index=1)
        score = self._make_score(8.0)
        trade_id = _insert_dummy_trade(conn)
        signal_id = _insert_dummy_signal(conn, trade_id)

        result = trader.maybe_trade(trade, score, trade_id, signal_id)
        assert result.executed

        pos = db.get_open_positions(conn)[0]
        assert pos["outcome_index"] == 0  # flipped from 1 → 0
        assert abs(pos["entry_price"] - 0.60) < 0.001

    def test_duplicate_rejected(self):
        conn = _make_conn()
        config = _make_config(enabled=True)
        trader = PaperTrader(config, conn)

        trade = self._make_trade()
        score = self._make_score(8.0)

        # First trade succeeds
        tid1 = _insert_dummy_trade(conn)
        sid1 = _insert_dummy_signal(conn, tid1)
        r1 = trader.maybe_trade(trade, score, tid1, sid1)
        assert r1.executed

        # Same condition_id + outcome → rejected
        tid2 = _insert_dummy_trade(conn)
        sid2 = _insert_dummy_signal(conn, tid2)
        r2 = trader.maybe_trade(trade, score, tid2, sid2)
        assert not r2.executed
        assert "duplicate" in r2.reason

    def test_summary_stats(self):
        conn = _make_conn()
        config = _make_config(enabled=True)
        trader = PaperTrader(config, conn)

        stats = trader.get_summary_stats()
        assert stats["open_count"] == 0
        assert stats["deployed"] == 0.0

        # Add a position
        trade = self._make_trade()
        score = self._make_score(7.0)
        tid = _insert_dummy_trade(conn)
        sid = _insert_dummy_signal(conn, tid)
        trader.maybe_trade(trade, score, tid, sid)

        stats = trader.get_summary_stats()
        assert stats["open_count"] == 1
        assert stats["deployed"] == 5000.0  # base_position at score=7 (1.0×)
