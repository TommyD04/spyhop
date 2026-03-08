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

from rich.console import Console
from rich.panel import Panel

from spyhop.ingestor.rtds import stream_trades
from spyhop.profiler.market import MarketCache
from spyhop.profiler.wallet import WalletCache
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


def _format_wallet_label(trade: dict[str, Any]) -> Text:
    """Show display name or pseudonym if available, otherwise truncated address."""
    name = trade.get("name") or trade.get("pseudonym") or ""
    addr = trade.get("wallet", "")
    if name:
        label = name[:14]
    else:
        label = _truncate_wallet(addr)
    return Text(label)


def _format_wlt(trade: dict[str, Any]) -> Text:
    """Format wallet trade count column with freshness highlighting."""
    count = trade.get("wallet_trade_count")
    if count is None:
        return Text("-", style="dim")
    if count <= 2:
        return Text(str(count), style="bold red")
    if count <= 5:
        return Text(str(count), style="yellow")
    label = "6+" if count == 6 else str(count)
    return Text(label, style="dim")


def _build_table(trades: deque[dict[str, Any]], trade_count: int, connected: bool) -> Table:
    """Build the Rich table from current trade buffer."""
    status = "[green]● Connected[/]" if connected else "[red]● Disconnected[/]"
    title = f"Spyhop — Whale Tracker  {status}  |  {trade_count} trades"

    table = Table(title=title, expand=True, show_lines=False)
    table.add_column("Time", style="dim", width=8, no_wrap=True)
    table.add_column("Wallet", width=15, no_wrap=True)
    table.add_column("Wlt", justify="right", width=4, no_wrap=True)
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
            _format_wallet_label(trade),
            _format_wlt(trade),
            side_text,
            _format_amount(trade["usdc_size"]),
            _format_price(trade.get("price", 0)),
            trade.get("market_question", "") or trade.get("condition_id", "")[:12],
        )

    if not trades:
        table.add_row("", "", "", "", "", "", "[dim]Waiting for whale trades...[/]")

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

    # Shared httpx client for both caches (connection pooling)
    client = httpx.AsyncClient(timeout=10.0)

    market_cache = MarketCache(
        conn=conn,
        client=client,
        gamma_url=config["market_cache"]["gamma_url"],
        ttl_minutes=config["market_cache"]["ttl_minutes"],
    )

    prof_cfg = config["profiler"]
    wallet_cache = WalletCache(
        conn=conn,
        client=client,
        data_api_url=prof_cfg["data_api_url"],
        ttl_minutes=prof_cfg["wallet_cache_ttl_minutes"],
        max_trades=prof_cfg["max_trades_to_fetch"],
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

        # Enrich with wallet profile (shallow — 1 HTTP call)
        wallet_addr = trade.get("wallet")
        if wallet_addr:
            profile = await wallet_cache.get_profile(wallet_addr, depth="shallow")
            if profile:
                trade["wallet_trade_count"] = profile.trade_count
                trade["wallet_is_fresh"] = profile.is_fresh

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
            await client.aclose()

    log.info("Watch stopped. %d trades recorded.", trade_count)


async def wallet_lookup(config: dict[str, Any], conn: sqlite3.Connection, address: str) -> None:
    """Deep-fetch a wallet profile and display it with recent trades."""
    console = Console()

    client = httpx.AsyncClient(timeout=15.0)
    prof_cfg = config["profiler"]
    wallet_cache = WalletCache(
        conn=conn,
        client=client,
        data_api_url=prof_cfg["data_api_url"],
        ttl_minutes=prof_cfg["wallet_cache_ttl_minutes"],
        max_trades=prof_cfg["max_trades_to_fetch"],
    )

    try:
        console.print(f"\n[dim]Fetching profile for[/] {address[:10]}...", end="")
        profile = await wallet_cache.get_profile(address, depth="deep")

        if not profile:
            console.print(" [red]failed[/]")
            console.print("[red]Could not fetch wallet profile. Check the address.[/]")
            return

        console.print(" [green]done[/]\n")

        # Build profile panel
        name_line = profile.display_name or profile.pseudonym or "[dim]anonymous[/]"
        fresh_label = "[bold red]YES[/]" if profile.is_fresh else "[green]No[/]"

        info = (
            f"[bold]Address:[/]       {profile.proxy_wallet}\n"
            f"[bold]Name:[/]          {name_line}\n"
            f"[bold]Trade Count:[/]   {profile.trade_count}\n"
            f"[bold]Unique Markets:[/] {profile.unique_markets}\n"
            f"[bold]First Trade:[/]   {profile.first_trade_ts or 'unknown'}\n"
            f"[bold]Fresh Wallet:[/]  {fresh_label}\n"
            f"[bold]Profile Depth:[/] {profile.profile_depth}"
        )
        console.print(Panel(info, title="Wallet Profile", border_style="blue"))

        # Fetch and display recent trades
        recent = await wallet_cache.fetch_recent_trades(address, limit=20)
        if recent:
            table = Table(title="Recent Trades", expand=True)
            table.add_column("Time", style="dim", width=19, no_wrap=True)
            table.add_column("Market", ratio=1)
            table.add_column("Side", width=4, no_wrap=True)
            table.add_column("USDC", justify="right", width=10, no_wrap=True)
            table.add_column("Price", justify="right", width=7, no_wrap=True)

            for t in recent:
                side = str(t.get("side", "")).upper()
                side_text = Text(side)
                if side == "BUY":
                    side_text.stylize("green")
                elif side == "SELL":
                    side_text.stylize("red")

                size = float(t.get("size", 0))
                price = float(t.get("price", 0))
                usdc = size * price

                ts = t.get("timestamp") or t.get("matchTime") or ""
                title = t.get("title") or t.get("conditionId", "")[:16] or ""

                table.add_row(
                    str(ts)[:19],
                    title,
                    side_text,
                    _format_amount(usdc),
                    _format_price(price),
                )

            console.print(table)
        else:
            console.print("[dim]No recent trades found.[/]")

    finally:
        await client.aclose()
