"""Rich live display for whale trade streaming + detection scoring."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections import deque
from typing import Any

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spyhop.detector import build_scorer
from spyhop.detector.base import DetectionContext
from spyhop.ingestor.rtds import stream_trades
from spyhop.profiler.event import EventCache
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


def _format_mult(val: float | None) -> Text:
    """Format a detector multiplier: 2.5x in yellow, or dim dash if 1.0."""
    if val is None or val <= 1.0:
        return Text("-", style="dim")
    return Text(f"{val:.1f}x", style="yellow")


def _format_score(trade: dict[str, Any]) -> Text:
    """Format composite suspicion score with alert highlighting.

    Appends '$' if the trade triggered a paper entry.
    """
    score = trade.get("score")
    if score is None or score == 0:
        return Text("-", style="dim")
    label = f"{score:.1f}"
    if trade.get("paper_entry"):
        label += "$"
    if score >= 9:
        return Text(f"{label}!" if not trade.get("paper_entry") else label, style="bold red")
    if score >= 7:
        return Text(label, style="bold yellow")
    if score >= 4:
        return Text(label, style="yellow")
    return Text(label, style="dim")


_TAG_STYLES = {
    "Politics": "bright_cyan",
    "Sports": "bright_green",
    "Crypto": "bright_yellow",
    "Economy": "bright_blue",
}


def _format_tag(trade: dict[str, Any]) -> Text:
    """Format primary event category tag with color coding."""
    tag = trade.get("primary_tag", "")
    if not tag:
        return Text("-", style="dim")
    style = _TAG_STYLES.get(tag, "dim")
    return Text(tag[:8], style=style)


def _format_market(trade: dict[str, Any]) -> str:
    """Market question with outcome appended, e.g. 'O/U 6.5 → Under'."""
    question = trade.get("market_question", "") or trade.get("condition_id", "")[:12]
    outcome = trade.get("outcome", "")
    if outcome:
        return f"{question} → {outcome}"
    return question


def _build_table(
    trades: deque[dict[str, Any]],
    trade_count: int,
    connected: bool,
    paper_stats: dict[str, Any] | None = None,
) -> Table:
    """Build the Rich table from current trade buffer."""
    status = "[green]● Connected[/]" if connected else "[red]● Disconnected[/]"
    title = f"Spyhop — Whale Tracker  {status}  |  {trade_count} trades"
    if paper_stats:
        count = paper_stats["open_count"]
        deployed = paper_stats["deployed"]
        title += f"  |  {count} pos, ${deployed:,.0f} deployed"

    table = Table(title=title, expand=True, show_lines=False)
    table.add_column("Time", style="dim", width=8, no_wrap=True)
    table.add_column("Wallet", width=15, no_wrap=True)
    table.add_column("Wlt", justify="right", width=4, no_wrap=True)
    table.add_column("Cat", width=8, no_wrap=True)
    table.add_column("F", justify="right", width=4, no_wrap=True)
    table.add_column("S", justify="right", width=4, no_wrap=True)
    table.add_column("N", justify="right", width=4, no_wrap=True)
    table.add_column("Score", justify="right", width=5, no_wrap=True)
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
            _format_tag(trade),
            _format_mult(trade.get("fresh_wallet_mult")),
            _format_mult(trade.get("size_anomaly_mult")),
            _format_mult(trade.get("niche_market_mult")),
            _format_score(trade),
            side_text,
            _format_amount(trade["usdc_size"]),
            _format_price(trade.get("price", 0)),
            _format_market(trade),
        )

    if not trades:
        table.add_row("", "", "", "", "", "", "", "", "", "", "", "[dim]Waiting for whale trades...[/]")

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

    event_cache = EventCache(
        conn=conn,
        client=client,
        gamma_url=config["event_cache"]["gamma_url"],
        ttl_minutes=config["event_cache"]["ttl_minutes"],
    )

    prof_cfg = config["profiler"]
    wallet_cache = WalletCache(
        conn=conn,
        client=client,
        data_api_url=prof_cfg["data_api_url"],
        ttl_minutes=prof_cfg["wallet_cache_ttl_minutes"],
        max_trades=prof_cfg["max_trades_to_fetch"],
    )

    scorer = build_scorer(config)

    # Paper trading — lazy import, zero overhead when disabled
    paper_trader = None
    paper_stats: dict[str, Any] | None = None
    if config.get("paper", {}).get("enabled", False):
        from spyhop.paper.trader import PaperTrader
        paper_trader = PaperTrader(config, conn)
        paper_stats = paper_trader.get_summary_stats()

    live = Live(_build_table(trade_buffer, trade_count, connected, paper_stats),
                refresh_per_second=4)

    async def handle_trade(trade: dict[str, Any]) -> None:
        nonlocal trade_count, connected, paper_stats
        connected = True

        try:
            # Enrich with market metadata — always fetch for detector context
            market = None
            cid = trade.get("condition_id")
            if cid:
                market = await market_cache.get_market(cid, slug=trade.get("market_slug", ""))
                if market and not trade.get("market_question"):
                    trade["market_question"] = market.question

            # Enrich with event category tag
            event_slug = trade.get("event_slug")
            if event_slug:
                event = await event_cache.get_event(event_slug)
                if event:
                    trade["primary_tag"] = event.primary_tag

            # Enrich with wallet profile (shallow — 1 HTTP call)
            profile = None
            wallet_addr = trade.get("wallet")
            if wallet_addr:
                profile = await wallet_cache.get_profile(wallet_addr, depth="shallow")
                if profile:
                    trade["wallet_trade_count"] = profile.trade_count
                    trade["wallet_is_fresh"] = profile.is_fresh

            # Score (synchronous — no I/O, pure arithmetic)
            context = DetectionContext(trade=trade, wallet_profile=profile, market=market)
            score_result = scorer.score(context)
            trade["score"] = score_result.composite
            for sig in score_result.signals:
                trade[f"{sig.name}_mult"] = sig.multiplier

            # Persist trade
            trade_id = db.insert_trade(conn, trade)

            # Persist signal if any detector fired
            signal_id = None
            if score_result.composite > 0:
                # Map detector names to DB column prefixes
                _col_map = {"fresh_wallet": "fresh", "size_anomaly": "size",
                            "niche_market": "niche"}
                sig = {"trade_id": trade_id, "timestamp": trade["timestamp"],
                       "composite_score": score_result.composite,
                       "fresh_mult": 1.0, "fresh_detail": "",
                       "size_mult": 1.0, "size_detail": "",
                       "niche_mult": 1.0, "niche_detail": "",
                       "is_alert": int(score_result.alert),
                       "is_critical": int(score_result.critical)}
                for r in score_result.signals:
                    col = _col_map.get(r.name, r.name)
                    sig[f"{col}_mult"] = r.multiplier
                    sig[f"{col}_detail"] = r.detail
                signal_id = db.insert_signal(conn, sig)

            # Paper trading
            if paper_trader:
                paper_result = paper_trader.maybe_trade(
                    trade, score_result, trade_id, signal_id
                )
                if paper_result and paper_result.executed:
                    trade["paper_entry"] = True

        except Exception:
            log.exception("handle_trade error for %s — skipping",
                          trade.get("condition_id", "?")[:12])

        # Always update display buffer even if enrichment/scoring failed
        trade_buffer.appendleft(trade)
        trade_count += 1

        # Refresh paper stats periodically
        if paper_trader and (trade_count % 10 == 0 or trade.get("paper_entry")):
            paper_stats = paper_trader.get_summary_stats()

        live.update(_build_table(trade_buffer, trade_count, connected, paper_stats))

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


async def history_view(
    config: dict[str, Any], conn: sqlite3.Connection,
    limit: int = 50, min_score: float = 0.0,
) -> None:
    """Display past detection signals sorted by score."""
    console = Console()

    signals = db.get_recent_signals(conn, limit=limit, min_score=min_score)

    if not signals:
        console.print("[dim]No signals found.[/]")
        return

    table = Table(title=f"Detection Signals (min score {min_score})", expand=True)
    table.add_column("Time", style="dim", width=19, no_wrap=True)
    table.add_column("Wallet", width=13, no_wrap=True)
    table.add_column("Score", justify="right", width=5, no_wrap=True)
    table.add_column("F", justify="right", width=4, no_wrap=True)
    table.add_column("S", justify="right", width=4, no_wrap=True)
    table.add_column("N", justify="right", width=4, no_wrap=True)
    table.add_column("Amount", justify="right", width=10, no_wrap=True)
    table.add_column("Market", ratio=1)

    for s in signals:
        score = s["composite_score"]
        score_text = Text(f"{score:.1f}")
        if score >= 9:
            score_text.stylize("bold red")
        elif score >= 7:
            score_text.stylize("bold yellow")
        elif score >= 4:
            score_text.stylize("yellow")
        else:
            score_text.stylize("dim")

        def _mult_text(val: float) -> Text:
            if val > 1.0:
                return Text(f"{val:.1f}", style="yellow")
            return Text("-", style="dim")

        ts = s.get("timestamp", "")
        table.add_row(
            ts[:19],
            _truncate_wallet(s.get("wallet", "")),
            score_text,
            _mult_text(s.get("fresh_mult", 1.0)),
            _mult_text(s.get("size_mult", 1.0)),
            _mult_text(s.get("niche_mult", 1.0)),
            _format_amount(s.get("usdc_size", 0)),
            s.get("market_question", "") or s.get("condition_id", "")[:12],
        )

    console.print(table)


async def positions_view(
    config: dict[str, Any],
    conn: sqlite3.Connection,
    refresh: bool = False,
) -> None:
    """Display open paper trading positions with optional mark-to-market."""
    import json

    console = Console()
    positions = db.get_open_positions(conn)

    if not positions:
        console.print("[dim]No open paper positions.[/]")
        return

    # Build market prices from cached data (or refresh from API)
    market_prices: dict[str, list[float]] = {}
    if refresh:
        client = httpx.AsyncClient(timeout=10.0)
        from spyhop.profiler.market import MarketCache
        market_cache = MarketCache(
            conn=conn,
            client=client,
            gamma_url=config["market_cache"]["gamma_url"],
            ttl_minutes=0,  # force refresh
        )
        try:
            for pos in positions:
                cid = pos["condition_id"]
                if cid not in market_prices:
                    market = await market_cache.get_market(cid)
                    if market and market.outcome_prices:
                        market_prices[cid] = market.outcome_prices
        finally:
            await client.aclose()
    else:
        # Read cached prices from markets table
        for pos in positions:
            cid = pos["condition_id"]
            if cid not in market_prices:
                cached = db.get_market(conn, cid)
                if cached and cached.get("outcome_prices"):
                    try:
                        prices = json.loads(cached["outcome_prices"])
                        market_prices[cid] = [float(p) for p in prices]
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

    # Build table
    table = Table(title="Paper Positions (OPEN)", expand=True)
    table.add_column("Entry Time", style="dim", width=19, no_wrap=True)
    table.add_column("Market", ratio=1)
    table.add_column("Outcome", width=12, no_wrap=True)
    table.add_column("Entry", justify="right", width=7, no_wrap=True)
    table.add_column("Current", justify="right", width=7, no_wrap=True)
    table.add_column("Size", justify="right", width=10, no_wrap=True)
    table.add_column("Unrealized", justify="right", width=10, no_wrap=True)
    table.add_column("Score", justify="right", width=5, no_wrap=True)

    total_deployed = 0.0
    total_unrealized = 0.0

    for pos in positions:
        entry_price = pos["entry_price"]
        token_qty = pos["token_qty"]
        size_usd = pos["size_usd"]
        total_deployed += size_usd

        # Get current price
        prices = market_prices.get(pos["condition_id"])
        current_price = None
        if prices and len(prices) > pos["outcome_index"]:
            current_price = prices[pos["outcome_index"]]

        # Calculate unrealized P&L
        current_display = "\u2014"
        unrealized_display = Text("\u2014", style="dim")
        if current_price is not None:
            unrealized = (current_price - entry_price) * token_qty
            total_unrealized += unrealized
            current_display = f"{current_price * 100:.1f}\u00a2"
            pnl_str = f"${unrealized:+,.0f}"
            style = "green" if unrealized >= 0 else "red"
            unrealized_display = Text(pnl_str, style=style)

        question = pos.get("market_question", "") or pos["condition_id"][:20]

        table.add_row(
            pos["entry_timestamp"][:19],
            question[:50],
            pos["outcome"][:12],
            f"{entry_price * 100:.1f}\u00a2",
            current_display,
            f"${size_usd:,.0f}",
            unrealized_display,
            f"{pos['score_at_entry']:.1f}",
        )

    console.print(table)

    # Summary panel
    capital = config.get("paper", {}).get("starting_capital", 100_000)
    available = capital - total_deployed
    pnl_style = "green" if total_unrealized >= 0 else "red"
    pnl_str = f"${total_unrealized:+,.0f}"

    summary = (
        f"[bold]Starting Capital:[/]  ${capital:,.0f}\n"
        f"[bold]Deployed:[/]          ${total_deployed:,.0f}\n"
        f"[bold]Available:[/]         ${available:,.0f}\n"
        f"[bold]Open Positions:[/]    {len(positions)}\n"
        f"[bold]Unrealized P&L:[/]    [{pnl_style}]{pnl_str}[/]"
    )
    console.print(Panel(summary, title="Portfolio Summary", border_style="blue"))


def paper_reset(conn: sqlite3.Connection, confirm: bool = False) -> None:
    """Delete all paper positions after confirmation."""
    console = Console()

    count = db.count_open_positions(conn)
    total = conn.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]

    if total == 0:
        console.print("[dim]No paper positions to reset.[/]")
        return

    if not confirm:
        console.print(
            f"[yellow]This will delete {total} paper positions ({count} open).[/]"
        )
        response = input("Type 'yes' to confirm: ")
        if response.strip().lower() != "yes":
            console.print("[dim]Cancelled.[/]")
            return

    deleted = db.delete_all_paper_positions(conn)
    console.print(f"[green]Deleted {deleted} paper positions.[/]")
