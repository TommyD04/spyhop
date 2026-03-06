"""Gamma API market metadata cache."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from spyhop.storage import db


@dataclass
class Market:
    condition_id: str
    question: str
    slug: str
    volume: float
    volume_24hr: float
    outcome_prices: str  # JSON string, e.g. '[0.62, 0.38]'


class MarketCache:
    """Gamma API market metadata with SQLite-backed TTL cache."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        client: httpx.AsyncClient,
        gamma_url: str = "https://gamma-api.polymarket.com",
        ttl_minutes: int = 60,
    ) -> None:
        self._conn = conn
        self._client = client
        self._gamma_url = gamma_url.rstrip("/")
        self._ttl = timedelta(minutes=ttl_minutes)

    def _is_fresh(self, market_row: dict[str, Any]) -> bool:
        """Check whether a cached market entry is still within TTL."""
        fetched = datetime.fromisoformat(market_row["last_fetched"])
        return datetime.now(timezone.utc) - fetched < self._ttl

    async def get_market(self, condition_id: str) -> Market | None:
        """Look up market metadata, hitting Gamma API on cache miss/expiry."""
        # Check cache
        cached = db.get_market(self._conn, condition_id)
        if cached and self._is_fresh(cached):
            return self._row_to_market(cached)

        # Fetch from Gamma API
        market = await self._fetch_from_gamma(condition_id)
        if market:
            db.upsert_market(self._conn, {
                "condition_id": market.condition_id,
                "question": market.question,
                "slug": market.slug,
                "volume": market.volume,
                "volume_24hr": market.volume_24hr,
                "outcome_prices": market.outcome_prices,
                "last_fetched": datetime.now(timezone.utc).isoformat(),
            })
        return market

    async def _fetch_from_gamma(self, condition_id: str) -> Market | None:
        """Fetch a single market from the Gamma API."""
        try:
            resp = await self._client.get(
                f"{self._gamma_url}/markets",
                params={"condition_id": condition_id},
            )
            resp.raise_for_status()
            data = resp.json()

            # Gamma returns a list; take the first match
            if isinstance(data, list) and data:
                return self._parse_market(data[0])
            if isinstance(data, dict) and data.get("condition_id"):
                return self._parse_market(data)

            return None
        except (httpx.HTTPError, KeyError, IndexError):
            return None

    @staticmethod
    def _parse_market(raw: dict[str, Any]) -> Market:
        """Parse a Gamma API market response into a Market dataclass."""
        outcome_prices = raw.get("outcomePrices", raw.get("outcome_prices", "[]"))
        if isinstance(outcome_prices, list):
            outcome_prices = json.dumps(outcome_prices)

        return Market(
            condition_id=raw.get("conditionId", raw.get("condition_id", "")),
            question=raw.get("question", "Unknown market"),
            slug=raw.get("slug", ""),
            volume=float(raw.get("volume", 0) or 0),
            volume_24hr=float(raw.get("volume24hr", raw.get("volume_24hr", 0)) or 0),
            outcome_prices=outcome_prices,
        )

    @staticmethod
    def _row_to_market(row: dict[str, Any]) -> Market:
        return Market(
            condition_id=row["condition_id"],
            question=row["question"] or "Unknown market",
            slug=row["slug"] or "",
            volume=row["volume"] or 0.0,
            volume_24hr=row["volume_24hr"] or 0.0,
            outcome_prices=row["outcome_prices"] or "[]",
        )
