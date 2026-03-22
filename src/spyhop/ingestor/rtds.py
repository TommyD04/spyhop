"""RTDS WebSocket client — streams live Polymarket trades.

Protocol notes (discovered empirically, March 2026):
  - Subscribe with type "*" (wildcard) — "trades" type receives nothing.
  - Actual messages arrive as type "orders_matched".
  - Payload 'size' is in outcome tokens, not USDC. USDC value = size * price.
  - 'title' field contains human-readable market question.
  - Server requires application-level "PING" keepalive (text frame, not WS ping).
  - Known server bug: data stream freezes after ~20 min → silence timeout reconnect.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Awaitable
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.asyncio.client import connect

log = logging.getLogger(__name__)

# type "*" is required — "trades" receives no data; "orders_matched" is the actual type
SUBSCRIBE_MSG = json.dumps({
    "action": "subscribe",
    "subscriptions": [
        {"topic": "activity", "type": "*"}
    ],
})

PING_INTERVAL = 5       # seconds — required by RTDS protocol
SILENCE_TIMEOUT = 300   # seconds — reconnect if no data for 5 min (known server bug)
DEDUP_MAX_SIZE = 10_000  # max entries before clearing (~2.5 days at current volume)


class _Deduplicator:
    """In-memory dedup filter for RTDS duplicate messages.

    RTDS sends ~57% of orders_matched events twice (identical tx_hash,
    wallet, and asset_id within 0-2 seconds).  This filter sits between
    parse and on_trade() so duplicates never enter the enrichment/scoring
    pipeline.

    Uses a plain set with a size cap.  When the set fills up, it resets
    entirely — the oldest entries are hours/days old and irrelevant since
    duplicates arrive within seconds.  At ~4K trades/day above threshold,
    10K entries covers ~2.5 days with zero risk of false positives.
    """

    def __init__(self, max_size: int = DEDUP_MAX_SIZE) -> None:
        self._seen: set[tuple[str, str, str]] = set()
        self._max_size = max_size
        self._dupes_blocked = 0

    def is_duplicate(self, trade: dict[str, Any]) -> bool:
        """Return True if this trade has already been seen."""
        key = (
            trade.get("tx_hash", ""),
            trade.get("wallet", ""),
            trade.get("asset_id", ""),
        )
        # Skip dedup if key fields are empty (shouldn't happen, but safe)
        if not key[0]:
            return False

        if key in self._seen:
            self._dupes_blocked += 1
            return True

        if len(self._seen) >= self._max_size:
            log.info(
                "Dedup cache full (%d entries, %d dupes blocked) — resetting",
                len(self._seen), self._dupes_blocked,
            )
            self._seen.clear()
            self._dupes_blocked = 0

        self._seen.add(key)
        return False


def _parse_trade(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a normalized trade dict from an RTDS payload.

    RTDS 'size' is token quantity; USDC value = size * price.
    """
    try:
        # Timestamp: epoch seconds (int/float) or ISO string
        ts = raw.get("timestamp", "")
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        size = float(raw.get("size", 0))
        price = float(raw.get("price", 0))
        usdc_size = size * price  # Token qty × unit price = USDC cost

        return {
            "timestamp": str(ts),
            "wallet": raw.get("proxyWallet", ""),
            "side": str(raw.get("side", "")).upper(),
            "usdc_size": usdc_size,
            "price": price,
            "condition_id": raw.get("conditionId", ""),
            "asset_id": raw.get("asset", ""),
            "tx_hash": raw.get("transactionHash", ""),
            "market_question": raw.get("title", ""),  # RTDS includes market title
            "market_slug": raw.get("slug", ""),
            "name": raw.get("name", "") or "",
            "pseudonym": raw.get("pseudonym", "") or "",
            "outcome": raw.get("outcome", ""),
            "outcome_index": raw.get("outcomeIndex"),
            "event_slug": raw.get("eventSlug", ""),
        }
    except (ValueError, TypeError):
        return None


async def _pinger(ws) -> None:
    """Send application-level PING every 5s as required by RTDS protocol."""
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await ws.send("PING")
    except (asyncio.CancelledError, websockets.ConnectionClosed):
        pass


async def _silence_watchdog(ws, last_data: list[float], timeout: float) -> None:
    """Independent task that forces reconnect when data stream freezes.

    Must run as a separate asyncio task — checking for silence inside
    ``async for msg in ws`` is dead code during actual silence because
    the loop is blocked waiting for the next message.
    """
    try:
        while True:
            await asyncio.sleep(timeout / 3)
            elapsed = asyncio.get_event_loop().time() - last_data[0]
            if elapsed > timeout:
                log.warning("Silence watchdog: no data for %ds — forcing reconnect",
                            int(elapsed))
                await ws.close()
                return
    except (asyncio.CancelledError, websockets.ConnectionClosed):
        pass


async def stream_trades(
    config: dict[str, Any],
    on_trade: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Connect to RTDS WebSocket and stream whale trades.

    Runs indefinitely with auto-reconnect. Call via asyncio task;
    cancel the task or raise KeyboardInterrupt to stop.
    """
    ws_url = config["ingestor"]["ws_url"]
    threshold = config["ingestor"]["usd_threshold"]
    delay = config["ingestor"]["reconnect_delay_sec"]

    # Dedup filter — persists across reconnects since RTDS can send a
    # duplicate straddling a disconnect/reconnect boundary
    dedup = _Deduplicator()

    while True:
        ping_task = None
        watchdog_task = None
        try:
            log.info("Connecting to RTDS: %s", ws_url)
            async with connect(ws_url) as ws:
                await ws.send(SUBSCRIBE_MSG)
                log.info("Subscribed to activity/* (threshold $%s)", f"{threshold:,.0f}")

                # Start application-level keepalive
                ping_task = asyncio.create_task(_pinger(ws))

                # Mutable ref so the message loop can update, watchdog can read
                last_data = [asyncio.get_event_loop().time()]
                watchdog_task = asyncio.create_task(
                    _silence_watchdog(ws, last_data, SILENCE_TIMEOUT)
                )

                async for raw_msg in ws:
                    # Skip empty acks and pong responses
                    if not raw_msg or raw_msg in ("pong", "PONG"):
                        continue

                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue

                    # Only process messages with payload
                    if not isinstance(msg, dict) or "payload" not in msg:
                        continue

                    # Update silence tracker (read by watchdog task)
                    last_data[0] = asyncio.get_event_loop().time()

                    payload = msg["payload"]
                    if not isinstance(payload, dict):
                        continue

                    trade = _parse_trade(payload)
                    if trade and trade["usdc_size"] >= threshold:
                        if dedup.is_duplicate(trade):
                            log.debug("Dedup: skipping duplicate %s",
                                      trade["tx_hash"][:12])
                            continue
                        try:
                            await on_trade(trade)
                        except Exception:
                            log.exception("on_trade callback error — continuing stream")

        except websockets.ConnectionClosed as e:
            log.warning("WebSocket closed: %s — reconnecting in %ds", e, delay)
        except OSError as e:
            log.warning("Connection error: %s — reconnecting in %ds", e, delay)
        except asyncio.CancelledError:
            log.info("Stream cancelled, shutting down")
            if ping_task:
                ping_task.cancel()
            if watchdog_task:
                watchdog_task.cancel()
            return
        finally:
            if ping_task:
                ping_task.cancel()
            if watchdog_task:
                watchdog_task.cancel()

        await asyncio.sleep(delay)
