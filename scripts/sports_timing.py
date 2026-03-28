"""Sports timing analysis: how close to resolution were bets placed?

Uses signal_ts vs market end_date to compute hours-to-resolution,
then cross-tabs with win rate and entry price.

Usage:
    cd C:\\Users\\thoma\\Projects\\spyhop
    python scripts/sports_timing.py
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from spyhop.config import db_path
from spyhop.storage.db import init_db


def classify(sig: dict) -> None:
    side = sig["side"]
    oi = sig["outcome_index"] or 0
    ep = sig["entry_price"] or 0
    if side == "SELL":
        sig["effective_entry"] = 1.0 - ep
        eff_oi = 1 - oi
    else:
        sig["effective_entry"] = ep
        eff_oi = oi
    try:
        prices = json.loads(sig["outcome_prices"] or "[]")
        exit_p = float(prices[eff_oi])
    except (json.JSONDecodeError, IndexError, TypeError, ValueError):
        sig["result"] = "OPEN"
        return
    if exit_p >= 0.99:
        sig["result"] = "WIN"
        ee = sig["effective_entry"]
        sig["pnl_pct"] = (1.0 - ee) / ee * 100 if ee > 0 else 0
    elif exit_p <= 0.01:
        sig["result"] = "LOSS"
        sig["pnl_pct"] = -100.0
    else:
        sig["result"] = "OPEN"
        sig["pnl_pct"] = 0.0


def hours_to_resolution(signal_ts: str, end_date: str | None) -> float | None:
    """Compute hours between signal timestamp and market end_date."""
    if not end_date:
        return None
    try:
        sig_dt = datetime.fromisoformat(signal_ts)
        if sig_dt.tzinfo is None:
            sig_dt = sig_dt.replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        delta = (end_dt - sig_dt).total_seconds() / 3600
        return delta
    except (ValueError, TypeError):
        return None


def sport_league(slug: str) -> str:
    slug = (slug or "").lower()
    if slug.startswith("nba-"):
        return "NBA"
    if slug.startswith("nhl-"):
        return "NHL"
    if slug.startswith("cbb-"):
        return "CBB"
    if slug.startswith("lol-"):
        return "LoL"
    if slug.startswith("cs2-"):
        return "CS2"
    if slug.startswith("dota2-"):
        return "Dota2"
    if slug.startswith(("epl-", "ucl-", "elc-", "itsb-")):
        return "Soccer"
    if slug.startswith("atp-"):
        return "Tennis"
    return "Other"


def main() -> None:
    conn = init_db(db_path())

    rows = conn.execute(
        """SELECT s.composite_score, s.timestamp AS signal_ts,
                  s.fresh_mult, s.niche_mult,
                  t.side, t.price AS entry_price, t.condition_id,
                  t.outcome_index, t.market_question, t.usdc_size, t.wallet,
                  m.outcome_prices, m.slug, m.end_date
           FROM signals s
           JOIN trades t ON s.trade_id = t.id
           LEFT JOIN markets m ON t.condition_id = m.condition_id
           WHERE s.is_alert = 1
             AND t.condition_id IS NOT NULL AND t.condition_id != ''
           ORDER BY s.composite_score DESC"""
    ).fetchall()

    signals = [dict(r) for r in rows]

    for sig in signals:
        slug = sig.get("slug", "")
        if slug:
            ev = conn.execute(
                "SELECT primary_tag FROM events "
                "WHERE ? LIKE event_slug || '%' "
                "ORDER BY LENGTH(event_slug) DESC LIMIT 1",
                (slug,),
            ).fetchone()
            sig["category"] = ev["primary_tag"] if ev else "Unknown"
        else:
            sig["category"] = "Unknown"

    for sig in signals:
        classify(sig)
        sig["league"] = sport_league(sig.get("slug", ""))
        sig["hrs_to_res"] = hours_to_resolution(sig["signal_ts"], sig.get("end_date"))

    sports = [s for s in signals if s["category"] == "Sports" and s["result"] in ("WIN", "LOSS")]

    # How many have timing data?
    with_timing = [s for s in sports if s["hrs_to_res"] is not None]
    without_timing = [s for s in sports if s["hrs_to_res"] is None]
    print(f"Resolved Sports: {len(sports)}")
    print(f"  With timing data:    {len(with_timing)}")
    print(f"  Missing end_date:    {len(without_timing)}")
    print()

    if not with_timing:
        print("No timing data available.")
        conn.close()
        return

    # Distribution of hours-to-resolution
    print("=" * 70)
    print("  HOURS TO RESOLUTION — distribution")
    print("=" * 70)
    for s in with_timing:
        h = s["hrs_to_res"]
        if h < 0:
            s["timing_label"] = "AFTER resolution"
        elif h < 1:
            s["timing_label"] = "<1h (in-play)"
        elif h < 3:
            s["timing_label"] = "1-3h (near game)"
        elif h < 6:
            s["timing_label"] = "3-6h (game day)"
        elif h < 24:
            s["timing_label"] = "6-24h (day before)"
        elif h < 72:
            s["timing_label"] = "1-3 days"
        else:
            s["timing_label"] = "3+ days"

    timing_order = [
        "AFTER resolution",
        "<1h (in-play)",
        "1-3h (near game)",
        "3-6h (game day)",
        "6-24h (day before)",
        "1-3 days",
        "3+ days",
    ]

    print(f"{'Timing':<24} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>9} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 75)
    for label in timing_order:
        grp = [s for s in with_timing if s["timing_label"] == label]
        if not grp:
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_entry = sum(s["effective_entry"] for s in grp) / len(grp)
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        risked = len(grp) * 100
        returned = sum(100 / s["effective_entry"] for s in grp
                       if s["result"] == "WIN" and s["effective_entry"] > 0)
        roi = (returned - risked) / risked * 100
        print(f"{label:<24} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% ${avg_entry:>7.2f} {avg_pnl:>+7.1f}% {roi:>+7.1f}%")
    print()

    # ── Timing x Entry Price ─────────────────────────────────
    print("=" * 70)
    print("  TIMING x ENTRY PRICE")
    print("=" * 70)
    for label in timing_order:
        grp = [s for s in with_timing if s["timing_label"] == label]
        if not grp:
            continue
        contrarian = [s for s in grp if s["effective_entry"] < 0.50]
        midline = [s for s in grp if 0.50 <= s["effective_entry"] < 0.55]
        favorite = [s for s in grp if s["effective_entry"] >= 0.55]
        print(f"\n  {label}:")
        for elabel, eg in [("Contrarian (<$0.50)", contrarian),
                           ("Midline ($0.50-0.55)", midline),
                           ("Favorite (>=$0.55)", favorite)]:
            if not eg:
                continue
            won = sum(1 for s in eg if s["result"] == "WIN")
            avg_pnl = sum(s["pnl_pct"] for s in eg) / len(eg)
            print(f"    {elabel:<28} {len(eg):>3} signals, "
                  f"{won} won ({won/len(eg)*100:>4.0f}% WR), P&L {avg_pnl:>+6.1f}%")
    print()

    # ── Timing x League ──────────────────────────────────────
    print("=" * 70)
    print("  TIMING x LEAGUE")
    print("=" * 70)
    leagues = sorted(set(s["league"] for s in with_timing))
    for league in leagues:
        grp = [s for s in with_timing if s["league"] == league]
        if len(grp) < 3:
            continue
        print(f"\n  {league} ({len(grp)} signals):")
        for label in timing_order:
            sub = [s for s in grp if s["timing_label"] == label]
            if not sub:
                continue
            won = sum(1 for s in sub if s["result"] == "WIN")
            avg_entry = sum(s["effective_entry"] for s in sub) / len(sub)
            print(f"    {label:<24} {len(sub):>3} signals, "
                  f"{won} won ({won/len(sub)*100:>4.0f}% WR), "
                  f"avg entry ${avg_entry:.2f}")
    print()

    # ── Raw data: show actual hours for manual inspection ────
    print("=" * 70)
    print("  RAW TIMING DATA (sorted by hours to resolution)")
    print("=" * 70)
    print(f"{'Hrs':>7} {'Score':>5} {'Entry':>6} {'W/L':>4} {'League':<8} Market")
    print("-" * 75)
    for s in sorted(with_timing, key=lambda x: x["hrs_to_res"]):
        q = (s["market_question"] or "")[:35]
        print(f"{s['hrs_to_res']:>7.1f} {s['composite_score']:>5.1f} "
              f"${s['effective_entry']:>.2f}  {s['result']:>4} "
              f"{s['league']:<8} {q}")

    # ── Composite: best sporty_investor filter with timing ───
    print()
    print("=" * 70)
    print("  COMPOSITE FILTERS WITH TIMING")
    print("=" * 70)

    # Get wallet signal counts for repeat filter
    wallet_counts: dict[str, int] = {}
    for s in sports:
        wallet_counts[s["wallet"]] = wallet_counts.get(s["wallet"], 0) + 1

    filters = [
        ("All with timing", lambda s: True),
        ("In-play (<1h)", lambda s: s["hrs_to_res"] is not None and s["hrs_to_res"] < 1),
        ("Near-game (1-3h)", lambda s: s["hrs_to_res"] is not None and 1 <= s["hrs_to_res"] < 3),
        ("Game day (<6h)", lambda s: s["hrs_to_res"] is not None and s["hrs_to_res"] < 6),
        ("Pre-game (6-24h)", lambda s: s["hrs_to_res"] is not None and 6 <= s["hrs_to_res"] < 24),
        ("Contrarian + <6h", lambda s: s["hrs_to_res"] is not None and s["hrs_to_res"] < 6 and s["effective_entry"] < 0.50),
        ("Contrarian + in-play", lambda s: s["hrs_to_res"] is not None and s["hrs_to_res"] < 1 and s["effective_entry"] < 0.50),
        ("Repeat(3+) + <6h", lambda s: s["hrs_to_res"] is not None and s["hrs_to_res"] < 6 and wallet_counts.get(s["wallet"], 0) >= 3),
        ("Niche(2.0) + <6h", lambda s: s["hrs_to_res"] is not None and s["hrs_to_res"] < 6 and 1.9 <= s["niche_mult"] <= 2.1),
    ]
    print(f"{'Filter':<28} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 70)
    for label, fn in filters:
        grp = [s for s in with_timing if fn(s)]
        if not grp:
            print(f"{label:<28} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        risked = len(grp) * 100
        returned = sum(100 / s["effective_entry"] for s in grp
                       if s["result"] == "WIN" and s["effective_entry"] > 0)
        roi = (returned - risked) / risked * 100
        print(f"{label:<28} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}% {roi:>+7.1f}%")

    conn.close()


if __name__ == "__main__":
    main()
