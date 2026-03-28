"""Tests for V5 A1: Resolution poller — DB helpers, classification logic, and poller integration."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from spyhop.paper.resolver import ResolutionPoller
from spyhop.storage import db


# ── Test helpers ───────────────────────────────────────────


def _make_conn() -> sqlite3.Connection:
    """Create an in-memory DB with full schema + migrations."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db._SCHEMA)
    db._migrate(conn)
    return conn


_trade_seq = 0


def _insert_dummy_trade(conn: sqlite3.Connection, **kw) -> int:
    """Insert a minimal trade row, return its ID."""
    global _trade_seq
    _trade_seq += 1
    trade = {
        "timestamp": "2026-03-08T12:00:00Z",
        "wallet": "0xabc123",
        "side": "BUY",
        "usdc_size": 15000.0,
        "price": 0.60,
        "condition_id": "cond_001",
        "asset_id": "asset_001",
        "market_question": "Will Raptors win?",
        "tx_hash": f"0xtx{_trade_seq:06d}",
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


def _insert_position(conn: sqlite3.Connection, **kw) -> int:
    """Insert a paper position with sensible defaults, return its ID."""
    trade_id = _insert_dummy_trade(conn, **{k: v for k, v in kw.items() if k in {
        "condition_id", "outcome", "outcome_index", "wallet",
    }})
    signal_id = _insert_dummy_signal(conn, trade_id)

    pos = {
        "trade_id": trade_id,
        "signal_id": signal_id,
        "condition_id": "cond_001",
        "market_question": "Will Raptors win?",
        "outcome": "Yes",
        "outcome_index": 0,
        "side": "BUY",
        "entry_price": 0.60,
        "size_usd": 5000.0,
        "token_qty": 8333.33,
        "score_at_entry": 8.0,
        "wallet": "0xabc123",
        "entry_timestamp": "2026-03-08T12:00:00Z",
    }
    pos.update(kw)
    return db.insert_paper_position(conn, pos)


def _insert_market(conn: sqlite3.Connection, condition_id: str = "cond_001", **kw) -> None:
    """Insert a market cache entry."""
    market = {
        "condition_id": condition_id,
        "question": "Will Raptors win?",
        "slug": "raptors-win",
        "volume": 100000.0,
        "volume_24hr": 10000.0,
        "outcome_prices": '[0.60, 0.40]',
        "end_date": "2026-03-22",
        "last_fetched": "2026-03-21T00:00:00+00:00",
    }
    market.update(kw)
    db.upsert_market(conn, market)


# ── DB Helper Tests ────────────────────────────────────────


class TestResolutionDBHelpers:
    def test_get_open_condition_ids_empty(self):
        conn = _make_conn()
        result = db.get_open_position_condition_ids(conn)
        assert result == []

    def test_get_open_condition_ids_distinct(self):
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="market-a")
        _insert_market(conn, "cond_002", slug="market-b")

        # 3 positions on 2 condition_ids
        _insert_position(conn, condition_id="cond_001")
        _insert_position(conn, condition_id="cond_001")
        _insert_position(conn, condition_id="cond_002")

        result = db.get_open_position_condition_ids(conn)
        assert len(result) == 2
        cids = {r["condition_id"] for r in result}
        assert cids == {"cond_001", "cond_002"}
        # Should have slugs from markets table
        slugs = {r["slug"] for r in result}
        assert slugs == {"market-a", "market-b"}

    def test_get_open_condition_ids_excludes_resolved(self):
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="market-a")
        _insert_market(conn, "cond_002", slug="market-b")

        _insert_position(conn, condition_id="cond_001")
        pos_id = _insert_position(conn, condition_id="cond_002")
        # Resolve one position
        db.close_position(conn, pos_id, 1.0, "2026-03-22T00:00:00Z", 3333.33)

        result = db.get_open_position_condition_ids(conn)
        assert len(result) == 1
        assert result[0]["condition_id"] == "cond_001"

    def test_get_open_condition_ids_null_slug(self):
        conn = _make_conn()
        # Position without market row → slug is None
        _insert_position(conn, condition_id="cond_orphan")

        result = db.get_open_position_condition_ids(conn)
        assert len(result) == 1
        assert result[0]["condition_id"] == "cond_orphan"
        assert result[0]["slug"] is None

    def test_close_position_updates_fields(self):
        conn = _make_conn()
        pos_id = _insert_position(conn)

        db.close_position(conn, pos_id, 1.0, "2026-03-22T12:00:00Z", 3333.33)

        row = conn.execute(
            "SELECT * FROM paper_positions WHERE id = ?", (pos_id,)
        ).fetchone()
        assert row["status"] == "RESOLVED"
        assert row["exit_price"] == 1.0
        assert row["exit_timestamp"] == "2026-03-22T12:00:00Z"
        assert abs(row["realized_pnl"] - 3333.33) < 0.01

    def test_close_position_already_resolved(self):
        conn = _make_conn()
        pos_id = _insert_position(conn)

        # Close once
        db.close_position(conn, pos_id, 1.0, "2026-03-22T12:00:00Z", 3333.33)

        # Close again — should be no-op (WHERE status='OPEN' won't match)
        db.close_position(conn, pos_id, 0.0, "2026-03-23T00:00:00Z", -5000.0)

        row = conn.execute(
            "SELECT * FROM paper_positions WHERE id = ?", (pos_id,)
        ).fetchone()
        # Original close values preserved
        assert row["exit_price"] == 1.0
        assert abs(row["realized_pnl"] - 3333.33) < 0.01

    def test_get_positions_for_condition(self):
        conn = _make_conn()
        _insert_position(conn, condition_id="cond_001")
        _insert_position(conn, condition_id="cond_001")
        _insert_position(conn, condition_id="cond_002")

        result = db.get_open_positions_for_condition(conn, "cond_001")
        assert len(result) == 2

        # Resolve one
        db.close_position(conn, result[0]["id"], 1.0, "2026-03-22T00:00:00Z", 1000.0)
        result2 = db.get_open_positions_for_condition(conn, "cond_001")
        assert len(result2) == 1


# ── Resolution Classification Tests ───────────────────────


class TestResolutionClassification:
    """Test P&L math and WIN/LOSS classification via _resolve_position."""

    def _make_poller(self, conn):
        return ResolutionPoller(conn)

    def test_win_pnl_math(self):
        conn = _make_conn()
        _insert_position(conn, entry_price=0.60, token_qty=10000.0)

        poller = self._make_poller(conn)
        pos = db.get_open_positions_for_condition(conn, "cond_001")[0]
        result = poller._resolve_position(pos, [1.0, 0.0])

        assert result is not None
        assert result.outcome == "WIN"
        assert result.entry_price == 0.60
        assert result.exit_price == 1.0
        assert abs(result.realized_pnl - 4000.0) < 0.01  # (1.0 - 0.6) * 10000

    def test_loss_pnl_math(self):
        conn = _make_conn()
        _insert_position(conn, entry_price=0.60, token_qty=10000.0)

        poller = self._make_poller(conn)
        pos = db.get_open_positions_for_condition(conn, "cond_001")[0]
        result = poller._resolve_position(pos, [0.0, 1.0])

        assert result is not None
        assert result.outcome == "LOSS"
        assert result.exit_price == 0.0
        assert abs(result.realized_pnl - (-6000.0)) < 0.01  # (0.0 - 0.6) * 10000

    def test_classify_win_loss(self):
        conn = _make_conn()

        # WIN case: exit >= 0.99
        _insert_position(
            conn, condition_id="cond_win",
            entry_price=0.50, token_qty=100,
        )
        poller = self._make_poller(conn)
        pos = db.get_open_positions_for_condition(conn, "cond_win")[0]
        result = poller._resolve_position(pos, [0.99, 0.01])
        assert result.outcome == "WIN"

        # LOSS case: exit <= 0.01
        _insert_position(
            conn, condition_id="cond_loss",
            entry_price=0.50, token_qty=100,
        )
        pos = db.get_open_positions_for_condition(conn, "cond_loss")[0]
        result = poller._resolve_position(pos, [0.01, 0.99])
        assert result.outcome == "LOSS"

    @pytest.mark.parametrize("entry_price", [0.10, 0.50, 0.90])
    def test_pnl_various_entries(self, entry_price: float):
        conn = _make_conn()
        qty = 10000.0

        # WIN
        cid_w = f"cond_win_{entry_price}"
        _insert_position(conn, condition_id=cid_w, entry_price=entry_price, token_qty=qty)
        poller = self._make_poller(conn)
        pos = db.get_open_positions_for_condition(conn, cid_w)[0]
        result = poller._resolve_position(pos, [1.0, 0.0])
        expected_pnl = (1.0 - entry_price) * qty
        assert abs(result.realized_pnl - expected_pnl) < 0.01

        # LOSS
        cid_l = f"cond_loss_{entry_price}"
        _insert_position(conn, condition_id=cid_l, entry_price=entry_price, token_qty=qty)
        pos = db.get_open_positions_for_condition(conn, cid_l)[0]
        result = poller._resolve_position(pos, [0.0, 1.0])
        expected_pnl = (0.0 - entry_price) * qty
        assert abs(result.realized_pnl - expected_pnl) < 0.01


# ── Poller Integration Tests (mocked httpx) ───────────────


def _gamma_response(
    condition_id: str = "cond_001",
    slug: str = "raptors-win",
    outcome_prices: list | None = None,
    closed: bool = False,
    question: str = "Will Raptors win?",
) -> list[dict]:
    """Build a Gamma API response list."""
    if outcome_prices is None:
        outcome_prices = [0.60, 0.40]
    return [{
        "conditionId": condition_id,
        "slug": slug,
        "question": question,
        "volume": "100000",
        "volume24hr": "10000",
        "outcomePrices": json.dumps(outcome_prices),
        "endDateIso": "2026-03-22",
        "closed": closed,
    }]


def _mock_httpx_response(status_code: int, json_data=None) -> httpx.Response:
    """Create an httpx.Response with a request attached (required for raise_for_status)."""
    request = httpx.Request("GET", "https://gamma-api.polymarket.com/markets")
    return httpx.Response(status_code, json=json_data, request=request)


class TestResolutionPoller:
    @pytest.mark.asyncio
    async def test_no_open_positions(self):
        """Empty DB → 0 checked, 0 resolved, no API calls."""
        conn = _make_conn()
        poller = ResolutionPoller(conn, request_delay_seconds=0)
        result = await poller.poll_once()
        assert result.markets_checked == 0
        assert result.markets_resolved == 0
        assert result.positions_resolved == 0

    @pytest.mark.asyncio
    async def test_resolves_winner(self):
        """Gamma returns closed + [1.0, 0.0] → position RESOLVED with positive pnl."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(conn, condition_id="cond_001", entry_price=0.56, token_qty=8928.57)

        mock_response = _mock_httpx_response(
            200, _gamma_response(closed=True, outcome_prices=[1.0, 0.0])
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.markets_checked == 1
        assert result.markets_resolved == 1
        assert result.positions_resolved == 1
        assert len(result.resolutions) == 1

        res = result.resolutions[0]
        assert res.outcome == "WIN"
        assert res.exit_price == 1.0
        assert res.realized_pnl > 0  # (1.0 - 0.56) * 8928.57

        # Verify DB state
        positions = db.get_open_positions(conn)
        assert len(positions) == 0
        row = conn.execute("SELECT * FROM paper_positions WHERE id = 1").fetchone()
        assert row["status"] == "RESOLVED"

    @pytest.mark.asyncio
    async def test_resolves_loser(self):
        """Gamma returns closed + [0.0, 1.0] → exit_price=0.0, pnl negative."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(conn, condition_id="cond_001", entry_price=0.60, token_qty=10000.0)

        mock_response = _mock_httpx_response(
            200, _gamma_response(closed=True, outcome_prices=[0.0, 1.0])
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.positions_resolved == 1
        res = result.resolutions[0]
        assert res.outcome == "LOSS"
        assert res.exit_price == 0.0
        assert res.realized_pnl < 0  # (0.0 - 0.6) * 10000 = -6000

    @pytest.mark.asyncio
    async def test_skips_open_market(self):
        """Gamma returns prices=[0.60, 0.40] → position stays OPEN."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(conn, condition_id="cond_001")

        mock_response = _mock_httpx_response(
            200, _gamma_response(closed=False, outcome_prices=[0.60, 0.40])
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.markets_checked == 1
        assert result.markets_resolved == 0
        assert result.positions_resolved == 0
        assert db.count_open_positions(conn) == 1

    @pytest.mark.asyncio
    async def test_boundary_prices_no_closed_flag(self):
        """prices=[1.0, 0.0] but closed=False → still resolves (boundary detection)."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(conn, condition_id="cond_001", entry_price=0.60, token_qty=10000.0)

        mock_response = _mock_httpx_response(
            200, _gamma_response(closed=False, outcome_prices=[1.0, 0.0])
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.markets_resolved == 1
        assert result.positions_resolved == 1
        assert result.resolutions[0].outcome == "WIN"

    @pytest.mark.asyncio
    async def test_gamma_error_continues(self):
        """HTTP 500 for one market, 200 for another → first skipped, second processed."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="market-a")
        _insert_market(conn, "cond_002", slug="market-b")
        _insert_position(conn, condition_id="cond_001")
        _insert_position(conn, condition_id="cond_002", entry_price=0.50, token_qty=10000.0)

        error_response = _mock_httpx_response(500)
        success_response = _mock_httpx_response(
            200,
            _gamma_response(
                condition_id="cond_002", slug="market-b",
                closed=True, outcome_prices=[1.0, 0.0],
            ),
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            # First call errors, second succeeds
            mock_client.get.side_effect = [
                httpx.HTTPStatusError(
                    "500", request=httpx.Request("GET", ""),
                    response=error_response,
                ),
                success_response,
            ]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.errors >= 1
        # The successful market should have been processed
        assert result.positions_resolved >= 1

    @pytest.mark.asyncio
    async def test_no_slug_skips(self):
        """Position without slug in markets → skipped with warning."""
        conn = _make_conn()
        # Position with no market row → slug will be None in join
        _insert_position(conn, condition_id="cond_orphan")

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.errors == 1
        assert result.markets_checked == 0
        # No HTTP calls should have been made
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_condition_id_mismatch(self):
        """Gamma returns wrong conditionId → skipped."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(conn, condition_id="cond_001")

        # Gamma returns a different conditionId (slug collision)
        mock_response = _mock_httpx_response(
            200,
            _gamma_response(condition_id="cond_WRONG", slug="raptors-win"),
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.errors == 1
        assert result.markets_resolved == 0
        assert db.count_open_positions(conn) == 1  # unchanged

    @pytest.mark.asyncio
    async def test_outcome_index_1(self):
        """Position on outcome 1 → correct exit_price selected."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(
            conn, condition_id="cond_001",
            outcome_index=1, entry_price=0.40, token_qty=12500.0,
        )

        mock_response = _mock_httpx_response(
            200, _gamma_response(closed=True, outcome_prices=[0.0, 1.0])
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.positions_resolved == 1
        res = result.resolutions[0]
        assert res.exit_price == 1.0  # outcome_prices[1]
        assert res.outcome == "WIN"
        assert abs(res.realized_pnl - 7500.0) < 0.01  # (1.0 - 0.4) * 12500

    @pytest.mark.asyncio
    async def test_resolves_across_theses(self):
        """Insider + sporty_investor positions both resolved correctly."""
        conn = _make_conn()
        _insert_market(conn, "cond_001", slug="raptors-win")
        _insert_position(
            conn, condition_id="cond_001",
            thesis="insider", entry_price=0.56, token_qty=8928.57,
        )
        _insert_position(
            conn, condition_id="cond_001",
            thesis="sporty_investor", entry_price=0.45, token_qty=6666.67,
        )

        mock_response = _mock_httpx_response(
            200, _gamma_response(closed=True, outcome_prices=[1.0, 0.0])
        )

        poller = ResolutionPoller(conn, request_delay_seconds=0)
        with patch("spyhop.paper.resolver.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await poller.poll_once()

        assert result.positions_resolved == 2
        theses = {r.thesis for r in result.resolutions}
        assert theses == {"insider", "sporty_investor"}
        # Both should be wins
        assert all(r.outcome == "WIN" for r in result.resolutions)

    @pytest.mark.asyncio
    async def test_run_forever_survives_exception(self):
        """poll_once raises → loop continues to next cycle."""
        conn = _make_conn()
        poller = ResolutionPoller(conn, poll_interval_minutes=0.001, request_delay_seconds=0)

        call_count = 0
        original_poll = poller.poll_once

        async def mock_poll():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated failure")
            if call_count >= 3:
                raise asyncio.CancelledError()  # stop the loop
            return await original_poll()

        poller.poll_once = mock_poll

        with pytest.raises(asyncio.CancelledError):
            await poller.run_forever()

        # Loop survived the first exception and made it to call 3
        assert call_count >= 3


# ── Market closed column tests ─────────────────────────────


class TestMarketClosedColumn:
    def test_upsert_market_default_closed(self):
        conn = _make_conn()
        _insert_market(conn, "cond_001")
        row = conn.execute("SELECT closed FROM markets WHERE condition_id = 'cond_001'").fetchone()
        assert row["closed"] == 0

    def test_upsert_market_with_closed(self):
        conn = _make_conn()
        _insert_market(conn, "cond_001", closed=1)
        row = conn.execute("SELECT closed FROM markets WHERE condition_id = 'cond_001'").fetchone()
        assert row["closed"] == 1
