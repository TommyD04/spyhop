"""Rich live display for whale trade streaming."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections import deque
from typing import Any

import httpx
from rich.live import Live
from rich.table import Table
from rich.text import Text

from spyhop.ingestor.rtds import stream_trades
from spyhop.profiler.market import MarketCache
from spyhop.storage import db

log = logging.getLogger(__name__)


def _truncate_wallet(addr: str) -> str:
    """0x7a3f...9d2e format."""
    if len(addr) > 12:
        return f"{addr[:6]}...{addr[-4:]}"
    return addr


def _format_amount(usdc: float) -> str:
    """$45,200 format."""
    return f"${usdc:,.0f}"


def _format_price(price: float) -> str:
    """Display as cents, e.g. 62.5¢."""
    return f"{price * 100:.1f}¢" if price else "—"


def _build_table(trades: deque[dict[str, Any]], trade_count: int, connected: bool) -> Table:
    """Build the Rich table from current trade buffer."""
    status = "[green]● Connected[/]" if connected else "[red]● Disconnected[/]"
    title = f"Spyhop — Whale Tracker  {status}  |  {trade_count} trades"

    table = Table(title=title, expand=True, show_lines=False)
    table.add_column("Time", style="dim", width=8, no_wrap=True)
    table.add_column("Wallet", width=13, no_wrap=True)
    table.add_column("Side", width=4, no_wrap=True)
    table.add_column("Amount", justify="right", width=10, no_wrap=True)
    table.add_column("Price", justify="right", width=7, no_wrap=True)
    table.add_column("Market", ratio=1)

    for trade in trades:
        side_text = Text(trade["side"])
        if trade["side"] == "BUY":
            side_text.stylize("green")
        elif trade["side"] == "SELL":
            side_text.stylize("red")

        # Extract HH:MM:SS from timestamp
        ts = trade.get("timestamp", "")
        time_display = ts[11:19] if len(ts) >= 19 else ts[:8]

        table.add_row(
            time_display,
            _truncate_wallet(trade.get("wallet", "")),
            side_text,
            _format_amount(trade["usdc_size"]),
            _format_price(trade.get("price", 0)),
            trade.get("market_question", "") or trade.get("condition_id", "")[:12],
        )

    if not trades:
        table.add_row("", "", "", "", "", "[dim]Waiting for whale trades...[/]")

    return table


async def watch(config: dict[str, Any], conn: sqlite3.Connection) -> None:
    """Main watch loop — stream trades and display in Rich live table."""
    max_rows = config["display"]["max_rows"]
    trade_buffer: deque[dict[str, Any]] = deque(maxlen=max_rows)
    trade_count = 0
    connected = False

    # Load recent trades from DB to pre-fill display
    recent = db.get_recent_trades(conn, max_rows)
    for t in reversed(recent):
        trade_buffer.appendleft(t)
    trade_count = len(recent)

    market_cache = MarketCache(
        conn=conn,
        client=httpx.AsyncClient(timeout=10.0),
        gamma_url=config["market_cache"]["gamma_url"],
        ttl_minutes=config["market_cache"]["ttl_minutes"],
    )

    live = Live(_build_table(trade_buffer, trade_count, connected), refresh_per_second=4)

    async def handle_trade(trade: dict[str, Any]) -> None:
        nonlocal trade_count, connected
        connected = True

        # Enrich with market metadata only if RTDS didn't include it
        if not trade.get("market_question") and trade.get("condition_id"):
            market = await market_cache.get_market(trade["condition_id"])
            if market:
                trade["market_question"] = market.question

        # Persist
        db.insert_trade(conn, trade)

        # Update display buffer
        trade_buffer.appendleft(trade)
        trade_count += 1
        live.update(_build_table(trade_buffer, trade_count, connected))

    with live:
        stream_task = asyncio.create_task(stream_trades(config, handle_trade))

        try:
            # stream_trades runs forever; await it so CancelledError propagates
            await stream_task
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            await market_cache._client.aclose()

    log.info("Watch stopped. %d trades recorded.", trade_count)
