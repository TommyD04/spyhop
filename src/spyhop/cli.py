"""Rich live display for whale trade streaming + detection scoring."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spyhop.detector import build_scorer, build_sports_scorer
from spyhop.detector.base import DetectionContext, ScoreResult
from spyhop.ingestor.rtds import stream_trades
from spyhop.paper.resolver import ResolutionPoller
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

    Appends 's' suffix for sporty_investor scores (different scale/thresholds).
    Appends '$' if the trade triggered a paper entry.
    """
    score = trade.get("score")
    if score is None or score == 0:
        return Text("-", style="dim")
    label = f"{score:.1f}"
    if trade.get("thesis") == "sporty_investor":
        label += "s"
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


_THESIS_ABBREV = {
    "insider": "IN",
    "sporty_investor": "SP",
}


def _format_thesis(trade: dict[str, Any]) -> Text:
    """Format thesis abbreviation: IN (insider) or SP (sporty_investor)."""
    thesis = trade.get("thesis", "")
    abbrev = _THESIS_ABBREV.get(thesis, "")
    if not abbrev:
        return Text("-", style="dim")
    if thesis == "sporty_investor":
        return Text(abbrev, style="bright_green")
    return Text(abbrev, style="dim")


def _format_market(trade: dict[str, Any]) -> str:
    """Market question with outcome appended, e.g. 'O/U 6.5 → Under'."""
    question = trade.get("market_question", "") or trade.get("condition_id", "")[:12]
    outcome = trade.get("outcome", "")
    if outcome:
        return f"{question} → {outcome}"
    return question


def _format_pnl(amount: float) -> Text:
    """Format a P&L value as $+12,400 (green) or $-3,200 (red)."""
    style = "green" if amount >= 0 else "red"
    return Text(f"${amount:+,.0f}", style=style)


def _format_time_to_close(
    end_date_str: str | None,
    *,
    _now: datetime | None = None,
) -> Text:
    """Format time remaining until market close as a human-readable string.

    Returns e.g. '2h', '1d 4h', '45m', dim 'past', dim '—' (no data).
    Accepts an optional _now for deterministic testing.

    Normalizes naive end_date strings (e.g. Gamma's bare '2026-06-30' dates)
    to UTC — mandatory per project timezone rule to avoid silent comparison errors.
    """
    if not end_date_str:
        return Text("—", style="dim")
    try:
        dt = datetime.fromisoformat(end_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = _now or datetime.now(timezone.utc)
        total_seconds = (dt - now).total_seconds()
        if total_seconds < 0:
            return Text("past", style="dim")
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        days = hours // 24
        rem_hours = hours % 24
        if days > 0:
            label = f"{days}d {rem_hours}h"
        elif hours > 0:
            label = f"{hours}h"
        else:
            label = f"{minutes}m"
        style = "yellow" if total_seconds < 3600 else ""
        return Text(label, style=style) if style else Text(label)
    except (ValueError, TypeError):
        return Text("?", style="dim")


def _compute_mtm(
    pos: dict[str, Any],
    cached_prices_json: str | None,
) -> tuple[float | None, str]:
    """Compute mark-to-market for an open position using cached outcome prices.

    Returns (unrealized_pnl, current_price_display).
    Both are None / '—' when price data is unavailable.
    """
    if not cached_prices_json:
        return None, "—"
    try:
        prices = [float(p) for p in json.loads(cached_prices_json)]
        idx = pos["outcome_index"]
        if idx >= len(prices):
            return None, "—"
        current = prices[idx]
        unrealized = (current - pos["entry_price"]) * pos["token_qty"]
        return unrealized, f"{current * 100:.1f}\u00a2"
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return None, "—"


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
    table.add_column("Th", width=2, no_wrap=True)
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
            _format_thesis(trade),
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
        table.add_row(
            "", "", "", "", "", "", "", "", "", "", "", "",
            "[dim]Waiting for whale trades...[/]",
        )

    return table


def _thesis_accepts(thesis_cfg: dict[str, Any], category: str) -> bool:
    """Check if a trade's category matches this thesis's routing rules.

    Rules:
    - If categories is non-empty, trade must match one of them.
    - If exclude_categories is non-empty, trade must NOT match any.
    - Empty categories = accept all (minus exclusions).
    """
    include = thesis_cfg.get("categories", [])
    exclude = thesis_cfg.get("exclude_categories", [])
    if include and category not in include:
        return False
    if exclude and category in exclude:
        return False
    return True


def _build_signal_dict(
    trade_id: int,
    trade: dict[str, Any],
    score_result: ScoreResult,
    thesis: str,
) -> dict[str, Any]:
    """Build a signal dict for db.insert_signal().

    Insider signals populate the legacy fresh/size/niche columns.
    Other theses set them to 1.0 and store all detector data in detector_results.
    """

    sig: dict[str, Any] = {
        "trade_id": trade_id,
        "timestamp": trade["timestamp"],
        "composite_score": score_result.composite,
        "fresh_mult": 1.0, "fresh_detail": "",
        "size_mult": 1.0, "size_detail": "",
        "niche_mult": 1.0, "niche_detail": "",
        "is_alert": int(score_result.alert),
        "is_critical": int(score_result.critical),
        "thesis": thesis,
    }

    if thesis == "insider":
        # Legacy column mapping for backward compat
        _col_map = {"fresh_wallet": "fresh", "size_anomaly": "size",
                     "niche_market": "niche"}
        for r in score_result.signals:
            col = _col_map.get(r.name, r.name)
            sig[f"{col}_mult"] = r.multiplier
            sig[f"{col}_detail"] = r.detail
        sig["detector_results"] = None
    else:
        # Non-insider: store all detector data in JSON
        detector_data = {
            r.name: {"multiplier": r.multiplier, "detail": r.detail}
            for r in score_result.signals
        }
        sig["detector_results"] = json.dumps(detector_data)

    return sig


async def watch(config: dict[str, Any], conn: sqlite3.Connection) -> None:
    """Main watch loop — stream trades and display in Rich live table.

    Runs a dual pipeline: each incoming trade is routed to matching theses
    (insider and/or sporty_investor) based on its event category tag.
    """
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

    # ── Build thesis pipelines ──────────────────────────────────
    # Each thesis has: name, config, scorer, paper_trader (optional), accepts_fn
    thesis_pipelines: list[dict[str, Any]] = []

    thesis_configs = config.get("thesis", {})
    for thesis_name, thesis_cfg in thesis_configs.items():
        if not thesis_cfg.get("enabled", True):
            continue

        # Build scorer
        if thesis_name == "insider":
            scorer = build_scorer(config)
        elif thesis_name == "sporty_investor":
            scorer = build_sports_scorer(config)
        else:
            log.warning("Unknown thesis '%s' — skipping", thesis_name)
            continue

        # Build paper trader if enabled
        paper_trader = None
        if thesis_cfg.get("paper", {}).get("enabled", False):
            from spyhop.paper.trader import PaperTrader
            paper_trader = PaperTrader(config, conn, thesis=thesis_name)

        thesis_pipelines.append({
            "name": thesis_name,
            "config": thesis_cfg,
            "scorer": scorer,
            "paper_trader": paper_trader,
        })

    log.info("Loaded %d thesis pipelines: %s",
             len(thesis_pipelines),
             [t["name"] for t in thesis_pipelines])

    # Aggregate paper stats across all theses for dashboard
    def _get_paper_stats() -> dict[str, Any] | None:
        total_count = 0
        total_deployed = 0.0
        any_active = False
        for tp in thesis_pipelines:
            pt = tp["paper_trader"]
            if pt:
                any_active = True
                stats = pt.get_summary_stats()
                total_count += stats["open_count"]
                total_deployed += stats["deployed"]
        if any_active:
            return {"open_count": total_count, "deployed": total_deployed}
        return None

    paper_stats = _get_paper_stats()

    live = Live(_build_table(trade_buffer, trade_count, connected, paper_stats),
                refresh_per_second=4)

    async def handle_trade(trade: dict[str, Any]) -> None:
        nonlocal trade_count, connected, paper_stats
        connected = True

        try:
            # ── Enrich (shared, thesis-agnostic) ────────────────
            market = None
            cid = trade.get("condition_id")
            if cid:
                market = await market_cache.get_market(cid, slug=trade.get("market_slug", ""))
                if market and not trade.get("market_question"):
                    trade["market_question"] = market.question

            event_slug = trade.get("event_slug")
            if event_slug:
                event = await event_cache.get_event(event_slug)
                if event:
                    trade["primary_tag"] = event.primary_tag

            profile = None
            wallet_addr = trade.get("wallet")
            if wallet_addr:
                profile = await wallet_cache.get_profile(wallet_addr, depth="shallow")
                if profile:
                    trade["wallet_trade_count"] = profile.trade_count
                    trade["wallet_is_fresh"] = profile.is_fresh

            context = DetectionContext(trade=trade, wallet_profile=profile, market=market)

            # Persist trade (always, regardless of thesis)
            trade_id = db.insert_trade(conn, trade)

            # ── Route to matching theses ────────────────────────
            tag = trade.get("primary_tag", "")
            any_paper_entry = False

            for tp in thesis_pipelines:
                thesis_name = tp["name"]
                thesis_cfg = tp["config"]
                scorer = tp["scorer"]
                paper_trader = tp["paper_trader"]

                if not _thesis_accepts(thesis_cfg, tag):
                    continue

                # Score
                score_result = scorer.score(context)

                # Track highest score for display (across theses)
                if score_result.composite > trade.get("score", 0):
                    trade["score"] = score_result.composite
                    trade["thesis"] = thesis_name
                    for sig in score_result.signals:
                        trade[f"{sig.name}_mult"] = sig.multiplier

                # Persist signal if any detector fired
                signal_id = None
                if score_result.composite > 0:
                    sig_dict = _build_signal_dict(
                        trade_id, trade, score_result, thesis_name,
                    )
                    signal_id = db.insert_signal(conn, sig_dict)

                # Paper trading
                if paper_trader:
                    settle_delay = paper_trader.settle_delay
                    if settle_delay > 0 and score_result.composite >= paper_trader.min_score:
                        await asyncio.sleep(settle_delay)
                    paper_result = paper_trader.maybe_trade(
                        trade, score_result, trade_id, signal_id,
                    )
                    if paper_result and paper_result.executed:
                        any_paper_entry = True

            if any_paper_entry:
                trade["paper_entry"] = True

        except Exception:
            log.exception("handle_trade error for %s — skipping",
                          trade.get("condition_id", "?")[:12])

        # Always update display buffer even if enrichment/scoring failed
        trade_buffer.appendleft(trade)
        trade_count += 1

        # Refresh paper stats periodically
        if trade_count % 10 == 0 or trade.get("paper_entry"):
            paper_stats = _get_paper_stats()

        live.update(_build_table(trade_buffer, trade_count, connected, paper_stats))

    # Start background resolution poller if any paper trader is active
    any_paper_active = any(tp["paper_trader"] for tp in thesis_pipelines)
    resolution_task = None
    if any_paper_active:
        res_cfg = config.get("resolution", {})
        poller = ResolutionPoller(
            conn=conn,
            gamma_url=config["market_cache"]["gamma_url"],
            poll_interval_minutes=res_cfg.get("poll_interval_minutes", 15),
            request_delay_seconds=res_cfg.get("request_delay_seconds", 1.0),
        )
        resolution_task = asyncio.create_task(poller.run_forever())
        log.info("Background resolution poller started")

    with live:
        stream_task = asyncio.create_task(stream_trades(config, handle_trade))

        try:
            # stream_trades runs forever; await it so CancelledError propagates
            await stream_task
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            stream_task.cancel()
            if resolution_task:
                resolution_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            if resolution_task:
                try:
                    await resolution_task
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
    thesis: str | None = None,
) -> None:
    """Display past detection signals sorted by score.

    Optionally filter by thesis name (e.g. 'insider', 'sporty_investor').
    """
    console = Console()

    signals = db.get_recent_signals(conn, limit=limit, min_score=min_score, thesis=thesis)

    if not signals:
        filter_label = f" for thesis={thesis}" if thesis else ""
        console.print(f"[dim]No signals found{filter_label}.[/]")
        return

    title = f"Detection Signals (min score {min_score}"
    if thesis:
        abbrev = _THESIS_ABBREV.get(thesis, thesis)
        title += f", thesis={abbrev}"
    title += ")"

    table = Table(title=title, expand=True)
    table.add_column("Time", style="dim", width=19, no_wrap=True)
    table.add_column("Wallet", width=13, no_wrap=True)
    table.add_column("Th", width=2, no_wrap=True)
    table.add_column("Score", justify="right", width=5, no_wrap=True)
    table.add_column("F", justify="right", width=4, no_wrap=True)
    table.add_column("S", justify="right", width=4, no_wrap=True)
    table.add_column("N", justify="right", width=4, no_wrap=True)
    table.add_column("Amount", justify="right", width=10, no_wrap=True)
    table.add_column("Market", ratio=1)

    for s in signals:
        score = s["composite_score"]
        sig_thesis = s.get("thesis", "insider")
        score_label = f"{score:.1f}" + ("s" if sig_thesis == "sporty_investor" else "")
        score_text = Text(score_label)
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
        thesis_text = _format_thesis({"thesis": sig_thesis})

        table.add_row(
            ts[:19],
            _truncate_wallet(s.get("wallet", "")),
            thesis_text,
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
            f"{pos['score_at_entry']:.1f}" + ("s" if pos.get("thesis") == "sporty_investor" else ""),
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


async def report_view(config: dict[str, Any], conn: sqlite3.Connection) -> None:
    """Unified P&L dashboard: summary, open positions (MTM), resolved, score bands.

    Uses only cached DB data — no HTTP calls.
    """
    console = Console()

    open_positions = db.get_open_positions_with_market(conn)
    resolved_positions = db.get_resolved_positions(conn)
    score_bands = db.get_score_band_breakdown(conn)

    # Mark-to-market for open positions
    total_unrealized = 0.0
    mtm_cache: list[tuple[float | None, str]] = []
    for pos in open_positions:
        pnl, price_str = _compute_mtm(pos, pos.get("cached_outcome_prices"))
        mtm_cache.append((pnl, price_str))
        if pnl is not None:
            total_unrealized += pnl

    # Summary totals
    realized_pnl = sum((p["realized_pnl"] or 0.0) for p in resolved_positions)
    combined_pnl = realized_pnl + total_unrealized
    resolved_wins = sum(1 for p in resolved_positions if (p["realized_pnl"] or 0.0) > 0)
    resolved_losses = len(resolved_positions) - resolved_wins

    # Per-thesis breakdown
    thesis_realized: dict[str, float] = defaultdict(float)
    thesis_open_count: dict[str, int] = defaultdict(int)
    for p in resolved_positions:
        thesis_realized[p.get("thesis", "insider")] += (p["realized_pnl"] or 0.0)
    for p in open_positions:
        thesis_open_count[p.get("thesis", "insider")] += 1

    r_style = "green" if realized_pnl >= 0 else "red"
    u_style = "green" if total_unrealized >= 0 else "red"
    c_style = "green" if combined_pnl >= 0 else "red"

    thesis_lines = ""
    all_theses = sorted(set(list(thesis_realized.keys()) + list(thesis_open_count.keys())))
    for t in all_theses:
        abbrev = _THESIS_ABBREV.get(t, t)
        r = thesis_realized.get(t, 0.0)
        o = thesis_open_count.get(t, 0)
        ts = "green" if r >= 0 else "red"
        thesis_lines += f"\n[bold]{abbrev}:[/]             [{ts}]${r:+,.0f}[/] realized | {o} open"

    summary = (
        f"[bold]Realized P&L:[/]   [{r_style}]${realized_pnl:+,.0f}[/]\n"
        f"[bold]Unrealized P&L:[/] [{u_style}]${total_unrealized:+,.0f}[/]  (mark-to-market, cached prices)\n"
        f"[bold]Combined P&L:[/]   [{c_style}]${combined_pnl:+,.0f}[/]\n\n"
        f"[bold]Resolved:[/]       {len(resolved_positions)} ({resolved_wins}W / {resolved_losses}L)\n"
        f"[bold]Open:[/]           {len(open_positions)}"
        f"{thesis_lines}"
    )
    console.print(Panel(summary, title="P&L Summary", border_style="blue"))

    # Open positions table
    if open_positions:
        table = Table(title="Open Positions (soonest expiry first)", expand=True)
        table.add_column("Entry", style="dim", width=16, no_wrap=True)
        table.add_column("Market", ratio=1)
        table.add_column("Th", width=2, no_wrap=True)
        table.add_column("Score", justify="right", width=6, no_wrap=True)
        table.add_column("Entry\u00a2", justify="right", width=6, no_wrap=True)
        table.add_column("Now\u00a2", justify="right", width=6, no_wrap=True)
        table.add_column("Unrealized", justify="right", width=10, no_wrap=True)
        table.add_column("Closes", justify="right", width=8, no_wrap=True)

        for pos, (pnl, price_str) in zip(open_positions, mtm_cache):
            score = pos["score_at_entry"]
            thesis = pos.get("thesis", "insider")
            score_label = f"{score:.1f}" + ("s" if thesis == "sporty_investor" else "")
            if score >= 9:
                score_text = Text(score_label, style="bold red")
            elif score >= 7:
                score_text = Text(score_label, style="bold yellow")
            else:
                score_text = Text(score_label, style="yellow")

            unreal_text = _format_pnl(pnl) if pnl is not None else Text("\u2014", style="dim")
            question = (pos.get("market_question") or pos["condition_id"][:20])[:45]

            table.add_row(
                pos["entry_timestamp"][:16],
                question,
                _format_thesis({"thesis": thesis}),
                score_text,
                f"{pos['entry_price'] * 100:.1f}",
                price_str if price_str != "\u2014" else Text("\u2014", style="dim"),
                unreal_text,
                _format_time_to_close(pos.get("end_date")),
            )
        console.print(table)
    else:
        console.print("[dim]No open positions.[/]")

    # Resolved positions table
    if resolved_positions:
        table = Table(title="Resolved Positions (most recent first)", expand=True)
        table.add_column("Exit", style="dim", width=16, no_wrap=True)
        table.add_column("Market", ratio=1)
        table.add_column("Th", width=2, no_wrap=True)
        table.add_column("Score", justify="right", width=6, no_wrap=True)
        table.add_column("Entry\u00a2", justify="right", width=6, no_wrap=True)
        table.add_column("Exit\u00a2", justify="right", width=6, no_wrap=True)
        table.add_column("P&L", justify="right", width=10, no_wrap=True)
        table.add_column("", width=4, no_wrap=True)

        for pos in resolved_positions:
            score = pos["score_at_entry"]
            thesis = pos.get("thesis", "insider")
            score_label = f"{score:.1f}" + ("s" if thesis == "sporty_investor" else "")
            if score >= 9:
                score_text = Text(score_label, style="bold red")
            elif score >= 7:
                score_text = Text(score_label, style="bold yellow")
            else:
                score_text = Text(score_label, style="yellow")

            pnl = pos["realized_pnl"] or 0.0
            result_text = Text("WIN", style="green") if pnl > 0 else Text("LOSS", style="red")
            question = (pos.get("market_question") or pos["condition_id"][:20])[:45]

            table.add_row(
                (pos.get("exit_timestamp") or "")[:16],
                question,
                _format_thesis({"thesis": thesis}),
                score_text,
                f"{pos['entry_price'] * 100:.1f}",
                f"{(pos.get('exit_price') or 0.0) * 100:.1f}",
                _format_pnl(pnl),
                result_text,
            )
        console.print(table)
    else:
        console.print("[dim]No resolved positions yet.[/]")

    # Score band breakdown
    if score_bands:
        table = Table(title="Score Band Breakdown (resolved)", expand=True)
        table.add_column("Band", width=6, no_wrap=True)
        table.add_column("Count", justify="right", width=6, no_wrap=True)
        table.add_column("Wins", justify="right", width=5, no_wrap=True)
        table.add_column("Win%", justify="right", width=5, no_wrap=True)
        table.add_column("Total P&L", justify="right", width=11, no_wrap=True)
        table.add_column("Avg P&L", justify="right", width=10, no_wrap=True)

        for band in score_bands:
            bf = band["band_floor"]
            count = band["count"]
            wins = band["wins"]
            win_pct = wins / count * 100 if count > 0 else 0
            win_style = "green" if win_pct >= 50 else "red"

            table.add_row(
                f"{bf}\u2013{bf + 1}",
                str(count),
                str(wins),
                Text(f"{win_pct:.0f}%", style=win_style),
                _format_pnl(band["total_pnl"]),
                _format_pnl(band["avg_pnl"]),
            )
        console.print(table)


async def resolve_once(config: dict[str, Any], conn: sqlite3.Connection) -> None:
    """Run a single resolution cycle and print results."""
    console = Console()

    res_cfg = config.get("resolution", {})
    poller = ResolutionPoller(
        conn=conn,
        gamma_url=config["market_cache"]["gamma_url"],
        poll_interval_minutes=res_cfg.get("poll_interval_minutes", 15),
        request_delay_seconds=res_cfg.get("request_delay_seconds", 1.0),
    )

    console.print("[dim]Checking open positions for resolved markets...[/]")
    result = await poller.poll_once()

    if result.markets_checked == 0 and result.errors == 0:
        console.print("[dim]No open paper positions to check.[/]")
        return

    # Summary table
    table = Table(title="Resolution Cycle Results", expand=True)
    table.add_column("Metric", style="bold", width=25)
    table.add_column("Value", justify="right", width=15)

    table.add_row("Markets checked", str(result.markets_checked))
    table.add_row("Markets resolved", str(result.markets_resolved))
    table.add_row("Positions resolved", str(result.positions_resolved))
    table.add_row("Errors", str(result.errors))

    console.print(table)

    if result.resolutions:
        # Detail table for resolved positions
        detail = Table(title="Resolved Positions", expand=True)
        detail.add_column("ID", width=5, justify="right")
        detail.add_column("Thesis", width=8)
        detail.add_column("Market", ratio=1)
        detail.add_column("Result", width=6)
        detail.add_column("Entry", justify="right", width=7)
        detail.add_column("Exit", justify="right", width=7)
        detail.add_column("P&L", justify="right", width=12)

        total_pnl = 0.0
        for res in result.resolutions:
            total_pnl += res.realized_pnl
            pnl_str = f"${res.realized_pnl:+,.2f}"
            pnl_style = "green" if res.realized_pnl >= 0 else "red"
            outcome_style = "green" if res.outcome == "WIN" else "red"

            detail.add_row(
                str(res.position_id),
                res.thesis[:8],
                res.market_question[:50],
                Text(res.outcome, style=outcome_style),
                f"{res.entry_price * 100:.1f}\u00a2",
                f"{res.exit_price * 100:.1f}\u00a2",
                Text(pnl_str, style=pnl_style),
            )

        console.print(detail)

        pnl_style = "green" if total_pnl >= 0 else "red"
        console.print(
            f"\n[bold]Total realized P&L:[/] [{pnl_style}]${total_pnl:+,.2f}[/]"
        )
    else:
        console.print("[dim]No positions resolved this cycle.[/]")
