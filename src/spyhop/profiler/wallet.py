"""Data API wallet profiling with SQLite-backed TTL cache.

Mirrors profiler/market.py pattern: dataclass + cache class + TTL.

Shallow fetch (1 request, limit=6) is used in the watch hot path.
Deep fetch (paginated) is used by the `wallet` CLI command and V3 escalation.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from spyhop.storage import db

log = logging.getLogger(__name__)


@dataclass
class WalletProfile:
    proxy_wallet: str
    display_name: str | None
    pseudonym: str | None
    trade_count: int        # 0-5 for shallow, actual for deep
    first_trade_ts: str | None
    unique_markets: int
    profile_depth: str      # "shallow" | "deep"

    @property
    def is_fresh(self) -> bool:
        """A wallet with <= 5 prior trades is considered fresh."""
        return self.trade_count <= 5


class WalletCache:
    """Data API wallet profiler with SQLite-backed TTL cache."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        client: httpx.AsyncClient,
        data_api_url: str = "https://data-api.polymarket.com",
        ttl_minutes: int = 30,
        max_trades: int = 200,
    ) -> None:
        self._conn = conn
        self._client = client
        self._data_api_url = data_api_url.rstrip("/")
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_trades = max_trades

    def _is_fresh(self, row: dict[str, Any]) -> bool:
        """Check whether a cached wallet entry is still within TTL."""
        fetched = datetime.fromisoformat(row["last_fetched"])
        return datetime.now(timezone.utc) - fetched < self._ttl

    async def get_profile(
        self, wallet: str, depth: str = "shallow"
    ) -> WalletProfile | None:
        """Look up wallet profile, hitting Data API on cache miss/expiry.

        If cached as shallow but deep requested, re-fetches.
        """
        cached = db.get_wallet(self._conn, wallet)
        if cached and self._is_fresh(cached):
            cached_depth = cached["profile_depth"]
            if depth == "shallow" or cached_depth == "deep":
                return self._row_to_profile(cached)

        if depth == "deep":
            profile = await self._fetch_deep(wallet)
        else:
            profile = await self._fetch_shallow(wallet)

        if profile:
            db.upsert_wallet(self._conn, {
                "proxy_wallet": profile.proxy_wallet,
                "display_name": profile.display_name,
                "pseudonym": profile.pseudonym,
                "trade_count": profile.trade_count,
                "first_trade_ts": profile.first_trade_ts,
                "unique_markets": profile.unique_markets,
                "last_fetched": datetime.now(timezone.utc).isoformat(),
                "profile_depth": profile.profile_depth,
            })

        return profile

    async def _fetch_shallow(self, wallet: str) -> WalletProfile | None:
        """Single request: GET /trades?user=<addr>&limit=6."""
        try:
            resp = await self._client.get(
                f"{self._data_api_url}/trades",
                params={"user": wallet, "limit": 6},
            )
            resp.raise_for_status()
            trades = resp.json()

            if not isinstance(trades, list):
                return None

            trade_count = len(trades)
            name = None
            pseudonym = None
            first_ts = None
            condition_ids: set[str] = set()

            for t in trades:
                if not name:
                    name = t.get("name") or None
                if not pseudonym:
                    pseudonym = t.get("pseudonym") or None
                ts = t.get("timestamp") or t.get("matchTime")
                if ts:
                    if first_ts is None or str(ts) < str(first_ts):
                        first_ts = str(ts)
                cid = t.get("conditionId")
                if cid:
                    condition_ids.add(cid)

            return WalletProfile(
                proxy_wallet=wallet,
                display_name=name,
                pseudonym=pseudonym,
                trade_count=trade_count,
                first_trade_ts=first_ts,
                unique_markets=len(condition_ids),
                profile_depth="shallow",
            )

        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.debug("Shallow fetch failed for %s: %s", wallet[:10], e)
            return None

    async def _fetch_deep(self, wallet: str) -> WalletProfile | None:
        """Paginated fetch: GET /trades?user=<addr>&limit=200&offset=N."""
        all_trades: list[dict[str, Any]] = []
        offset = 0
        page_size = 200

        try:
            while offset < self._max_trades:
                resp = await self._client.get(
                    f"{self._data_api_url}/trades",
                    params={"user": wallet, "limit": page_size, "offset": offset},
                )
                resp.raise_for_status()
                page = resp.json()

                if not isinstance(page, list):
                    break

                all_trades.extend(page)

                if len(page) < page_size:
                    break
                offset += page_size

        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("Deep fetch failed for %s at offset %d: %s", wallet[:10], offset, e)
            if not all_trades:
                return None

        name = None
        pseudonym = None
        first_ts = None
        condition_ids: set[str] = set()

        for t in all_trades:
            if not name:
                name = t.get("name") or None
            if not pseudonym:
                pseudonym = t.get("pseudonym") or None
            ts = t.get("timestamp") or t.get("matchTime")
            if ts:
                if first_ts is None or str(ts) < str(first_ts):
                    first_ts = str(ts)
            cid = t.get("conditionId")
            if cid:
                condition_ids.add(cid)

        return WalletProfile(
            proxy_wallet=wallet,
            display_name=name,
            pseudonym=pseudonym,
            trade_count=len(all_trades),
            first_trade_ts=first_ts,
            unique_markets=len(condition_ids),
            profile_depth="deep",
        )

    async def fetch_recent_trades(
        self, wallet: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch recent raw trades for display (wallet command)."""
        try:
            resp = await self._client.get(
                f"{self._data_api_url}/trades",
                params={"user": wallet, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except httpx.HTTPError:
            return []

    @staticmethod
    def _row_to_profile(row: dict[str, Any]) -> WalletProfile:
        return WalletProfile(
            proxy_wallet=row["proxy_wallet"],
            display_name=row["display_name"],
            pseudonym=row["pseudonym"],
            trade_count=row["trade_count"],
            first_trade_ts=row["first_trade_ts"],
            unique_markets=row["unique_markets"],
            profile_depth=row["profile_depth"],
        )
