"""Resolution poller — closes paper positions when markets resolve."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from spyhop.profiler.market import MarketCache
from spyhop.storage import db

log = logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    """Outcome of resolving a single paper position."""

    position_id: int
    condition_id: str
    market_question: str
    thesis: str
    outcome: str  # "WIN" or "LOSS"
    entry_price: float
    exit_price: float
    realized_pnl: float


@dataclass
class ResolutionCycleResult:
    """Summary of a single poll_once() cycle."""

    markets_checked: int = 0
    markets_resolved: int = 0
    positions_resolved: int = 0
    resolutions: list[ResolutionResult] = field(default_factory=list)
    errors: int = 0


class ResolutionPoller:
    """Polls Gamma API for resolved markets and closes paper positions.

    Two entry points:
    - poll_once(): single cycle — check all open-position markets, close resolved ones.
    - run_forever(): background loop calling poll_once() every N minutes.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        gamma_url: str = "https://gamma-api.polymarket.com",
        poll_interval_minutes: float = 15,
        request_delay_seconds: float = 1.0,
    ) -> None:
        self._conn = conn
        self._gamma_url = gamma_url.rstrip("/")
        self._poll_interval = poll_interval_minutes * 60  # seconds
        self._request_delay = request_delay_seconds

    async def poll_once(self) -> ResolutionCycleResult:
        """One resolution cycle: fetch market data, close resolved positions."""
        result = ResolutionCycleResult()

        open_conditions = db.get_open_position_condition_ids(self._conn)
        if not open_conditions:
            log.debug("Resolution poller: no open positions to check")
            return result

        async with httpx.AsyncClient(timeout=15.0) as client:
            for i, row in enumerate(open_conditions):
                condition_id = row["condition_id"]
                slug = row["slug"]

                if not slug:
                    log.warning(
                        "Resolution poller: skipping %s (no slug in markets table)",
                        condition_id[:12],
                    )
                    result.errors += 1
                    continue

                try:
                    market_data = await self._fetch_market(client, slug)
                except Exception:
                    log.exception(
                        "Resolution poller: error fetching %s", slug[:40]
                    )
                    result.errors += 1
                    if i < len(open_conditions) - 1:
                        await asyncio.sleep(self._request_delay)
                    continue

                result.markets_checked += 1

                if market_data is None:
                    result.errors += 1
                    if i < len(open_conditions) - 1:
                        await asyncio.sleep(self._request_delay)
                    continue

                # Verify conditionId matches (slug collisions possible)
                if market_data["condition_id"] != condition_id:
                    log.warning(
                        "Resolution poller: slug %s returned wrong conditionId"
                        " %s, expected %s — skipping",
                        slug[:30], market_data["condition_id"][:12],
                        condition_id[:12],
                    )
                    result.errors += 1
                    if i < len(open_conditions) - 1:
                        await asyncio.sleep(self._request_delay)
                    continue

                # Update market cache with fresh data
                is_closed = market_data.pop("_closed", False)
                market_data["closed"] = int(is_closed)
                market_data["last_fetched"] = datetime.now(timezone.utc).isoformat()
                db.upsert_market(self._conn, market_data)

                # Check if market has resolved
                try:
                    prices = json.loads(market_data["outcome_prices"])
                    prices_at_boundary = bool(prices) and all(
                        float(p) >= 0.99 or float(p) <= 0.01 for p in prices
                    )
                except (json.JSONDecodeError, ValueError, TypeError):
                    prices_at_boundary = False
                    prices = []

                if not is_closed and not prices_at_boundary:
                    # Market still open
                    if i < len(open_conditions) - 1:
                        await asyncio.sleep(self._request_delay)
                    continue

                # Market resolved — close all open positions on it
                result.markets_resolved += 1
                positions = db.get_open_positions_for_condition(
                    self._conn, condition_id
                )

                for pos in positions:
                    resolution = self._resolve_position(pos, prices)
                    if resolution:
                        result.positions_resolved += 1
                        result.resolutions.append(resolution)

                if i < len(open_conditions) - 1:
                    await asyncio.sleep(self._request_delay)

        return result

    async def run_forever(self) -> None:
        """Background loop: poll_once() every interval, with error boundary."""
        log.info(
            "Resolution poller started (interval=%.0fm, delay=%.1fs)",
            self._poll_interval / 60,
            self._request_delay,
        )
        while True:
            try:
                cycle = await self.poll_once()
                if cycle.markets_checked > 0 or cycle.errors > 0:
                    log.info(
                        "Resolution cycle: checked=%d, resolved=%d mkts"
                        " / %d positions, errors=%d",
                        cycle.markets_checked,
                        cycle.markets_resolved,
                        cycle.positions_resolved,
                        cycle.errors,
                    )
                for res in cycle.resolutions:
                    log.info(
                        "Position resolved: #%d [%s] %s → %s, entry=%.2f, exit=%.2f, pnl=$%+,.2f",
                        res.position_id,
                        res.thesis,
                        res.market_question[:40],
                        res.outcome,
                        res.entry_price,
                        res.exit_price,
                        res.realized_pnl,
                    )
            except Exception:
                log.exception("Resolution poller cycle failed — continuing")

            await asyncio.sleep(self._poll_interval)

    def _resolve_position(
        self,
        pos: dict[str, Any],
        outcome_prices: list,
    ) -> ResolutionResult | None:
        """Close a single position using resolved outcome prices."""
        position_id = pos["id"]
        outcome_index = pos["outcome_index"]
        entry_price = pos["entry_price"]
        token_qty = pos["token_qty"]

        if outcome_index >= len(outcome_prices):
            log.error(
                "Resolution poller: outcome_index %d out of range for position %d (prices=%s)",
                outcome_index,
                position_id,
                outcome_prices,
            )
            return None

        exit_price = float(outcome_prices[outcome_index])
        realized_pnl = (exit_price - entry_price) * token_qty

        if exit_price >= 0.99:
            outcome_label = "WIN"
        elif exit_price <= 0.01:
            outcome_label = "LOSS"
        else:
            # Partial resolution (closed=true but prices not at 0/1)
            outcome_label = "WIN" if exit_price > entry_price else "LOSS"
            log.warning(
                "Position %d resolved at non-boundary price %.4f (entry=%.4f)",
                position_id,
                exit_price,
                entry_price,
            )

        exit_timestamp = datetime.now(timezone.utc).isoformat()
        db.close_position(
            self._conn, position_id, exit_price, exit_timestamp, realized_pnl
        )

        log.info(
            "Closed position %d: %s, exit=%.4f, pnl=$%+,.2f",
            position_id,
            outcome_label,
            exit_price,
            realized_pnl,
        )

        return ResolutionResult(
            position_id=position_id,
            condition_id=pos["condition_id"],
            market_question=pos.get("market_question", ""),
            thesis=pos.get("thesis", "insider"),
            outcome=outcome_label,
            entry_price=entry_price,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
        )

    async def _fetch_market(
        self, client: httpx.AsyncClient, slug: str
    ) -> dict[str, Any] | None:
        """Fetch a single market from Gamma API by slug.

        Returns a dict with market fields + '_closed' boolean, or None on failure.
        Uses MarketCache._parse_market() for consistent field parsing.
        """
        resp = await client.get(
            f"{self._gamma_url}/markets",
            params={"slug": slug},
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or not data:
            return None

        raw = data[0]
        market = MarketCache._parse_market(raw)

        return {
            "condition_id": market.condition_id,
            "question": market.question,
            "slug": market.slug,
            "volume": market.volume,
            "volume_24hr": market.volume_24hr,
            "outcome_prices": market.outcome_prices,
            "end_date": market.end_date,
            "_closed": raw.get("closed", False),
        }
