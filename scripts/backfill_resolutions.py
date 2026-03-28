"""A4: Backfill historical resolutions from Gamma API.

Refreshes market data for all markets with alert-level signals, then:
1. Creates paper positions in the DB for resolved insider signals that
   don't already have one.
2. Immediately closes those positions with the resolved outcome.
3. Prints a calibration report.

Use --dry-run to preview without writing to the DB.

Usage:
    cd C:\\Users\\thoma\\Projects\\spyhop
    python scripts/backfill_resolutions.py
    python scripts/backfill_resolutions.py --dry-run
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone

import httpx

# Fix Windows cp1252 console encoding for box-drawing chars
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Import from spyhop package (requires pip install -e . or PYTHONPATH)
from spyhop.config import db_path
from spyhop.storage.db import init_db, insert_paper_position, close_position, upsert_market

# Position sizing for backfilled insider positions
_BASE_POSITION_USD = 5_000.0
_ALERT_THRESHOLD = 7.0

GAMMA_URL = "https://gamma-api.polymarket.com"
REQUEST_DELAY = 1.0  # seconds between API calls


def fetch_market(client: httpx.Client, slug: str) -> dict | None:
    """Fetch a single market from Gamma API by slug. Returns parsed dict or None."""
    try:
        resp = client.get(f"{GAMMA_URL}/markets", params={"slug": slug})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        raw = data[0]

        outcome_prices = raw.get("outcomePrices", "[]")
        if isinstance(outcome_prices, list):
            outcome_prices = json.dumps(outcome_prices)

        return {
            "condition_id": raw.get("conditionId", raw.get("condition_id", "")),
            "question": raw.get("question", "Unknown market"),
            "slug": raw.get("slug", ""),
            "volume": float(raw.get("volume", 0) or 0),
            "volume_24hr": float(raw.get("volume24hr", raw.get("volume_24hr", 0)) or 0),
            "outcome_prices": outcome_prices,
            "end_date": raw.get("endDateIso") or raw.get("end_date") or None,
            "closed": raw.get("closed", False),
        }
    except httpx.HTTPError as e:
        print(f"  WARNING: HTTP error for slug={slug}: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"  WARNING: Parse error for slug={slug}: {e}")
        return None


def classify_signal(
    entry_price: float,
    side: str,
    outcome_index: int,
    outcome_prices: str,
) -> dict:
    """Classify a signal as WIN/LOSS/OPEN based on resolved outcome prices.

    Uses the same effective_outcome normalization as PaperTrader:
    SELL flips the outcome_index and entry_price so everything is expressed
    as a directional BUY bet.
    """
    # Normalize SELL → BUY (same logic as trader.py lines 150-153)
    if side == "SELL":
        effective_oi = 1 - outcome_index
        effective_entry = 1.0 - entry_price
    else:
        effective_oi = outcome_index
        effective_entry = entry_price

    # Guard against bad data
    if effective_entry <= 0:
        return {"result": "OPEN", "pnl_pct": 0.0, "effective_entry": 0.0, "exit_price": 0.0}

    try:
        resolved_prices = json.loads(outcome_prices)
        exit_price = float(resolved_prices[effective_oi])
    except (json.JSONDecodeError, IndexError, TypeError):
        return {"result": "OPEN", "pnl_pct": 0.0, "effective_entry": effective_entry, "exit_price": 0.0}

    if exit_price >= 0.99:
        result = "WIN"
        pnl_pct = (1.0 - effective_entry) / effective_entry * 100
    elif exit_price <= 0.01:
        result = "LOSS"
        pnl_pct = -100.0
    else:
        result = "OPEN"
        pnl_pct = (exit_price - effective_entry) / effective_entry * 100

    return {
        "result": result,
        "pnl_pct": pnl_pct,
        "effective_entry": effective_entry,
        "exit_price": exit_price,
    }


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no positions will be written to the DB\n")

    # ── Connect to DB ────────────────────────────────────────────
    path = db_path()
    print(f"Database: {path}")
    conn = init_db(path)

    # ── Step 1: Find all unique markets with alert signals ───────
    rows = conn.execute(
        """SELECT DISTINCT t.condition_id, m.slug
           FROM signals s
           JOIN trades t ON s.trade_id = t.id
           LEFT JOIN markets m ON t.condition_id = m.condition_id
           WHERE s.is_alert = 1
             AND t.condition_id IS NOT NULL
             AND t.condition_id != ''"""
    ).fetchall()

    markets = [(r["condition_id"], r["slug"] or "") for r in rows]
    print(f"Found {len(markets)} unique markets with alert signals\n")

    if not markets:
        print("No alert-level signals in the database. Nothing to backfill.")
        return

    # ── Step 2: Refresh each market from Gamma API ───────────────
    stats = {"refreshed": 0, "resolved": 0, "open": 0, "errors": 0, "no_slug": 0}

    client = httpx.Client(timeout=15.0)
    try:
        for i, (cid, slug) in enumerate(markets, 1):
            if not slug:
                print(f"  [{i}/{len(markets)}] SKIP {cid[:12]}... (no slug)")
                stats["no_slug"] += 1
                continue

            print(f"  [{i}/{len(markets)}] Fetching {slug[:50]}...", end=" ")
            market_data = fetch_market(client, slug)

            if market_data is None:
                print("ERROR")
                stats["errors"] += 1
            else:
                # Verify condition_id matches (avoid slug collisions)
                if market_data["condition_id"] != cid:
                    print(f"MISMATCH (got {market_data['condition_id'][:12]})")
                    stats["errors"] += 1
                else:
                    is_closed = market_data.pop("closed", False)

                    # Update market cache via existing upsert
                    market_data["last_fetched"] = datetime.now(timezone.utc).isoformat()
                    upsert_market(conn, market_data)
                    stats["refreshed"] += 1

                    # Check if resolved (closed=true or outcomePrices at 0/1)
                    try:
                        prices = json.loads(market_data["outcome_prices"])
                        prices_at_boundary = all(
                            float(p) >= 0.99 or float(p) <= 0.01 for p in prices
                        ) if prices else False
                    except (json.JSONDecodeError, ValueError):
                        prices_at_boundary = False

                    if is_closed or prices_at_boundary:
                        print("RESOLVED")
                        stats["resolved"] += 1
                    else:
                        print("OPEN")
                        stats["open"] += 1

            if i < len(markets):
                time.sleep(REQUEST_DELAY)
    finally:
        client.close()

    print()

    # ── Step 3: Query all alert signals with refreshed market data ─
    # Scoped to insider thesis only. LEFT JOIN paper_positions so we can skip
    # signals that already have a position (idempotent re-runs).
    signal_rows = conn.execute(
        """SELECT s.id AS signal_id, s.trade_id, s.composite_score,
                  s.timestamp AS signal_ts, s.thesis,
                  t.side, t.price AS entry_price, t.condition_id,
                  t.outcome_index, t.market_question, t.usdc_size,
                  t.wallet, t.outcome,
                  m.outcome_prices, m.end_date, m.slug,
                  pp.id AS existing_pos_id
           FROM signals s
           JOIN trades t ON s.trade_id = t.id
           LEFT JOIN markets m ON t.condition_id = m.condition_id
           LEFT JOIN paper_positions pp ON pp.signal_id = s.id
           WHERE s.is_alert = 1
             AND s.thesis = 'insider'
             AND t.condition_id IS NOT NULL
             AND t.condition_id != ''
           ORDER BY s.composite_score DESC"""
    ).fetchall()

    signals = [dict(r) for r in signal_rows]

    # ── Step 4: Look up categories from events table ──────────────
    for sig in signals:
        slug = sig.get("slug", "")
        if slug:
            event_row = conn.execute(
                """SELECT primary_tag FROM events
                   WHERE ? LIKE event_slug || '%'
                   ORDER BY LENGTH(event_slug) DESC
                   LIMIT 1""",
                (slug,),
            ).fetchone()
            sig["category"] = event_row["primary_tag"] if event_row else "Unknown"
        else:
            sig["category"] = "Unknown"

    # ── Step 5: Classify each signal ──────────────────────────────
    for sig in signals:
        if sig["outcome_prices"] and sig["entry_price"] is not None:
            cls = classify_signal(
                entry_price=sig["entry_price"],
                side=sig["side"],
                outcome_index=sig["outcome_index"] or 0,
                outcome_prices=sig["outcome_prices"],
            )
            sig.update(cls)
        else:
            sig["result"] = "OPEN"
            sig["pnl_pct"] = 0.0
            sig["effective_entry"] = sig.get("entry_price", 0.0)
            sig["exit_price"] = 0.0

    # ── Step 6: Write backfilled paper positions to DB ────────────
    now_ts = datetime.now(timezone.utc).isoformat()
    pos_created = 0
    pos_skipped_existing = 0
    pos_skipped_open = 0

    for sig in signals:
        # Only write resolved outcomes
        if sig["result"] not in ("WIN", "LOSS"):
            pos_skipped_open += 1
            continue

        # Skip if position already exists for this signal
        if sig.get("existing_pos_id"):
            pos_skipped_existing += 1
            continue

        entry = sig["effective_entry"]
        if entry <= 0:
            continue

        score = sig["composite_score"]
        size_usd = _BASE_POSITION_USD * (score / _ALERT_THRESHOLD)
        token_qty = size_usd / entry
        exit_price = 1.0 if sig["result"] == "WIN" else 0.0
        realized_pnl = (exit_price - entry) * token_qty

        # Determine outcome/outcome_index from trade (SELL-normalized to BUY direction)
        side = sig.get("side", "BUY")
        raw_oi = sig.get("outcome_index") or 0
        if side == "SELL":
            effective_oi = 1 - raw_oi
            normalized_side = "BUY"
        else:
            effective_oi = raw_oi
            normalized_side = "BUY"

        position = {
            "trade_id": sig["trade_id"],
            "signal_id": sig["signal_id"],
            "condition_id": sig["condition_id"],
            "market_question": sig.get("market_question", ""),
            "outcome": sig.get("outcome", "Yes"),
            "outcome_index": effective_oi,
            "side": normalized_side,
            "entry_price": entry,
            "size_usd": size_usd,
            "token_qty": token_qty,
            "score_at_entry": score,
            "wallet": sig.get("wallet", ""),
            "entry_timestamp": sig["signal_ts"],
            "thesis": "insider",
        }

        if not dry_run:
            pos_id = insert_paper_position(conn, position)
            close_position(conn, pos_id, exit_price, now_ts, realized_pnl)

        pos_created += 1

    print(f"\nBackfilled positions: {pos_created} created"
          f" | {pos_skipped_existing} already existed"
          f" | {pos_skipped_open} skipped (market still open)")
    if dry_run:
        print("(dry run — no writes made)")
    print()

    # ── Print Report ──────────────────────────────────────────────
    resolved = [s for s in signals if s["result"] in ("WIN", "LOSS")]
    open_sigs = [s for s in signals if s["result"] == "OPEN"]
    winners = [s for s in resolved if s["result"] == "WIN"]
    losers = [s for s in resolved if s["result"] == "LOSS"]

    print("=" * 60)
    print("  BACKFILL SUMMARY")
    print("=" * 60)
    print(f"Markets refreshed: {stats['refreshed']} "
          f"({stats['resolved']} resolved, {stats['open']} open, "
          f"{stats['errors']} errors, {stats['no_slug']} no slug)")
    print(f"Signals analyzed:  {len(signals)}")
    print(f"  Resolved: {len(resolved)} ({len(winners)} won, {len(losers)} lost)")
    print(f"  Open:     {len(open_sigs)}")
    print()

    if not resolved:
        print("No resolved signals to analyze. Try again after more markets resolve.")
        return

    # ── Resolved Outcomes by Score Band ───────────────────────────
    print("=" * 60)
    print("  RESOLVED OUTCOMES BY SCORE BAND")
    print("=" * 60)
    bands = [
        ("7.0-7.9", 7.0, 8.0),
        ("8.0-8.9", 8.0, 9.0),
        ("9.0-10.0", 9.0, 10.01),
    ]
    print(f"{'Band':<12} {'Resolved':>8} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry(W)':>12} {'AvgEntry(L)':>12}")
    print("-" * 60)
    for label, lo, hi in bands:
        band_resolved = [s for s in resolved if lo <= s["composite_score"] < hi]
        band_won = [s for s in band_resolved if s["result"] == "WIN"]
        band_lost = [s for s in band_resolved if s["result"] == "LOSS"]
        if band_resolved:
            win_pct = len(band_won) / len(band_resolved) * 100
            avg_entry_w = (
                sum(s["effective_entry"] for s in band_won) / len(band_won)
                if band_won else 0
            )
            avg_entry_l = (
                sum(s["effective_entry"] for s in band_lost) / len(band_lost)
                if band_lost else 0
            )
            print(f"{label:<12} {len(band_resolved):>8} {len(band_won):>5} {len(band_lost):>5} "
                  f"{win_pct:>5.1f}% "
                  f"{'$' + f'{avg_entry_w:.2f}' if band_won else 'n/a':>12} "
                  f"{'$' + f'{avg_entry_l:.2f}' if band_lost else 'n/a':>12}")
        else:
            print(f"{label:<12} {'0':>8} {'0':>5} {'0':>5} {'n/a':>6} {'n/a':>12} {'n/a':>12}")
    print()

    # ── Resolved Outcomes by Category ─────────────────────────────
    print("=" * 60)
    print("  RESOLVED OUTCOMES BY CATEGORY")
    print("=" * 60)
    categories = sorted(set(s["category"] for s in resolved))
    print(f"{'Category':<16} {'Resolved':>8} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>10}")
    print("-" * 60)
    for cat in categories:
        cat_resolved = [s for s in resolved if s["category"] == cat]
        cat_won = [s for s in cat_resolved if s["result"] == "WIN"]
        if cat_resolved:
            win_pct = len(cat_won) / len(cat_resolved) * 100
            avg_entry = sum(s["effective_entry"] for s in cat_resolved) / len(cat_resolved)
            print(f"{cat:<16} {len(cat_resolved):>8} {len(cat_won):>5} "
                  f"{len(cat_resolved) - len(cat_won):>5} {win_pct:>5.1f}% ${avg_entry:>8.2f}")
    print()

    # ── Score Band x Category Cross-Tabulation ────────────────────
    print("=" * 60)
    print("  SCORE BAND x CATEGORY")
    print("=" * 60)
    for label, lo, hi in bands:
        band_resolved = [s for s in resolved if lo <= s["composite_score"] < hi]
        if not band_resolved:
            continue
        band_cats = sorted(set(s["category"] for s in band_resolved))
        print(f"\n  {label}:")
        print(f"  {'Category':<16} {'Resolved':>8} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>10}")
        print(f"  {'-' * 54}")
        for cat in band_cats:
            cell = [s for s in band_resolved if s["category"] == cat]
            cell_won = [s for s in cell if s["result"] == "WIN"]
            win_pct = len(cell_won) / len(cell) * 100
            avg_entry = sum(s["effective_entry"] for s in cell) / len(cell)
            print(f"  {cat:<16} {len(cell):>8} {len(cell_won):>5} "
                  f"{len(cell) - len(cell_won):>5} {win_pct:>5.1f}% ${avg_entry:>8.2f}")
    print()

    # ── Entry Price Analysis ──────────────────────────────────────
    print("=" * 60)
    print("  ENTRY PRICE ANALYSIS (key recalibration data)")
    print("=" * 60)
    if winners:
        avg_w = sum(s["effective_entry"] for s in winners) / len(winners)
        print(f"Winners avg entry:  ${avg_w:.2f} (N={len(winners)})")
    if losers:
        avg_l = sum(s["effective_entry"] for s in losers) / len(losers)
        print(f"Losers avg entry:   ${avg_l:.2f} (N={len(losers)})")
    print()

    price_bands = [
        ("$0.00-0.30", 0.00, 0.30),
        ("$0.30-0.70", 0.30, 0.70),
        ("$0.70-0.85", 0.70, 0.85),
        ("$0.85-1.00", 0.85, 1.01),
    ]
    print(f"{'Entry Range':<16} {'Resolved':>8} {'Won':>5} {'Lost':>5} {'Win%':>6}")
    print("-" * 50)
    for label, lo, hi in price_bands:
        band = [s for s in resolved if lo <= s["effective_entry"] < hi]
        band_won = [s for s in band if s["result"] == "WIN"]
        if band:
            win_pct = len(band_won) / len(band) * 100
            print(f"{label:<16} {len(band):>8} {len(band_won):>5} "
                  f"{len(band) - len(band_won):>5} {win_pct:>5.1f}%")
        else:
            print(f"{label:<16} {'0':>8} {'0':>5} {'0':>5} {'n/a':>6}")
    print()

    # ── Raw Resolved Signals ──────────────────────────────────────
    print("=" * 60)
    print("  RAW RESOLVED SIGNALS")
    print("=" * 60)
    print(f"{'Score':>5} {'Entry':>6} {'Exit':>5} {'P&L%':>7} {'W/L':>4} {'Category':<12} Market")
    print("-" * 80)
    for s in sorted(resolved, key=lambda x: x["composite_score"], reverse=True):
        question = (s["market_question"] or "Unknown")[:40]
        print(
            f"{s['composite_score']:>5.1f} "
            f"${s['effective_entry']:>.2f}  "
            f"${s['exit_price']:>.2f} "
            f"{s['pnl_pct']:>+6.1f}% "
            f"{s['result']:>4} "
            f"{s['category']:<12} "
            f"{question}"
        )

    conn.close()
    print(f"\nDone. Database updated at {path}")


if __name__ == "__main__":
    main()
