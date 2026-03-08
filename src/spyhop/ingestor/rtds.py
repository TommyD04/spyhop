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
            "name": raw.get("name", "") or "",
            "pseudonym": raw.get("pseudonym", "") or "",
            "outcome": raw.get("outcome", ""),
            "outcome_index": raw.get("outcomeIndex"),
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

    while True:
        ping_task = None
        try:
            log.info("Connecting to RTDS: %s", ws_url)
            async with connect(ws_url) as ws:
                await ws.send(SUBSCRIBE_MSG)
                log.info("Subscribed to activity/* (threshold $%s)", f"{threshold:,.0f}")

                # Start application-level keepalive
                ping_task = asyncio.create_task(_pinger(ws))
                last_data = asyncio.get_event_loop().time()

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

                    # Update silence tracker
                    now = asyncio.get_event_loop().time()
                    if now - last_data > SILENCE_TIMEOUT:
                        log.warning("No data for %ds — forcing reconnect", SILENCE_TIMEOUT)
                        break
                    last_data = now

                    payload = msg["payload"]
                    if not isinstance(payload, dict):
                        continue

                    trade = _parse_trade(payload)
                    if trade and trade["usdc_size"] >= threshold:
                        await on_trade(trade)

        except websockets.ConnectionClosed as e:
            log.warning("WebSocket closed: %s — reconnecting in %ds", e, delay)
        except OSError as e:
            log.warning("Connection error: %s — reconnecting in %ds", e, delay)
        except asyncio.CancelledError:
            log.info("Stream cancelled, shutting down")
            if ping_task:
                ping_task.cancel()
            return
        finally:
            if ping_task:
                ping_task.cancel()

        await asyncio.sleep(delay)
