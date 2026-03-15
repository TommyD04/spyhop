"""Gamma API event metadata cache — provides category tags for trades."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from spyhop.storage import db

log = logging.getLogger(__name__)

# Broad category tags — used to pick primary_tag from the event's tag list.
# First tag matching this set wins; if none match, use the first tag as-is.
_BROAD_TAGS = {
    "Sports", "Politics", "Crypto", "Economy",
    "Science", "Culture", "Entertainment",
}


@dataclass
class Event:
    event_slug: str
    title: str
    tags: list[str]       # ["Politics", "France", "Elections"]
    primary_tag: str       # "Politics"


class EventCache:
    """Gamma API event metadata with SQLite-backed TTL cache."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        client: httpx.AsyncClient,
        gamma_url: str = "https://gamma-api.polymarket.com",
        ttl_minutes: int = 120,
    ) -> None:
        self._conn = conn
        self._client = client
        self._gamma_url = gamma_url.rstrip("/")
        self._ttl = timedelta(minutes=ttl_minutes)

    def _is_fresh(self, row: dict[str, Any]) -> bool:
        fetched = datetime.fromisoformat(row["last_fetched"])
        return datetime.now(timezone.utc) - fetched < self._ttl

    async def get_event(self, event_slug: str) -> Event | None:
        """Look up event metadata, hitting Gamma API on cache miss/expiry.

        Uses a two-step strategy:
        1. Exact match on event_slug (fast, indexed).
        2. Prefix fallback — market slugs often have outcome-specific suffixes
           (e.g. 'ucl-psg1-cfc1-2026-03-11-psg1') that don't match the parent
           event slug ('ucl-psg1-cfc1-2026-03-11').  The prefix lookup finds the
           longest cached event slug that is a prefix of the given slug.
        """
        if not event_slug:
            return None

        # Step 1: exact cache hit
        cached = db.get_event(self._conn, event_slug)
        if cached and self._is_fresh(cached):
            return self._row_to_event(cached)

        # Step 2: try Gamma API with the full slug (works when slug IS an event)
        event = await self._fetch_from_gamma(event_slug)
        if event:
            db.upsert_event(self._conn, {
                "event_slug": event.event_slug,
                "title": event.title,
                "tags": json.dumps(event.tags),
                "primary_tag": event.primary_tag,
                "last_fetched": datetime.now(timezone.utc).isoformat(),
            })
            return event

        # Step 3: prefix fallback — check if a cached event is a prefix of this slug
        cached = db.get_event_by_prefix(self._conn, event_slug)
        if cached and self._is_fresh(cached):
            return self._row_to_event(cached)

        return None

    async def _fetch_from_gamma(self, event_slug: str) -> Event | None:
        """Fetch event from Gamma API via GET /events?slug=<slug>."""
        try:
            resp = await self._client.get(
                f"{self._gamma_url}/events",
                params={"slug": event_slug},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return self._parse_event(data[0], event_slug)
        except httpx.HTTPError as e:
            log.debug("Gamma event fetch failed for %s: %s", event_slug, e)
        return None

    @staticmethod
    def _parse_event(raw: dict[str, Any], event_slug: str) -> Event:
        """Parse a Gamma API event response into an Event dataclass."""
        # Tags come as list of objects with 'label' key
        raw_tags = raw.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [
                t["label"] if isinstance(t, dict) and "label" in t else str(t)
                for t in raw_tags
            ]
        else:
            tags = []

        # Pick the first broad-category tag; fall back to first tag
        primary_tag = ""
        for tag in tags:
            if tag in _BROAD_TAGS:
                primary_tag = tag
                break
        if not primary_tag and tags:
            primary_tag = tags[0]

        return Event(
            event_slug=event_slug,
            title=raw.get("title", ""),
            tags=tags,
            primary_tag=primary_tag,
        )

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> Event:
        tags_raw = row.get("tags", "[]")
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        return Event(
            event_slug=row["event_slug"],
            title=row.get("title", ""),
            tags=tags,
            primary_tag=row.get("primary_tag", ""),
        )
