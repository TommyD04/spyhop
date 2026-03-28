"""Sporty Investor hypothesis validation.

Tests four axes against resolved sports outcomes:
  H1: Fresh wallet multiplier is uncorrelated (or anti-correlated) with wins
  H2: Entry price is the dominant predictor
  H3: Niche market multiplier is correlated with wins
  H4: Repeat wallets outperform fresh wallets

Usage:
    cd C:\\Users\\thoma\\Projects\\spyhop
    python scripts/sports_hypothesis.py
"""

from __future__ import annotations

import io
import json
import sys

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

    # Pull signals WITH detector sub-scores
    rows = conn.execute(
        """SELECT s.composite_score, s.fresh_mult, s.fresh_detail,
                  s.size_mult, s.size_detail, s.niche_mult, s.niche_detail,
                  t.side, t.price AS entry_price, t.condition_id,
                  t.outcome_index, t.market_question, t.usdc_size, t.wallet,
                  m.outcome_prices, m.slug, m.volume, m.volume_24hr
           FROM signals s
           JOIN trades t ON s.trade_id = t.id
           LEFT JOIN markets m ON t.condition_id = m.condition_id
           WHERE s.is_alert = 1
             AND t.condition_id IS NOT NULL AND t.condition_id != ''
           ORDER BY s.composite_score DESC"""
    ).fetchall()

    signals = [dict(r) for r in rows]

    # Category filter
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

    sports = [s for s in signals if s["category"] == "Sports" and s["result"] in ("WIN", "LOSS")]

    print(f"Dataset: {len(sports)} resolved Sports signals")
    print()

    # ══════════════════════════════════════════════════════════
    # H1: Fresh wallet multiplier vs outcome
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  H1: FRESH WALLET MULTIPLIER — does freshness predict wins?")
    print("=" * 70)
    fresh_buckets = [
        ("1.0 (not fresh)", 0.9, 1.1),
        ("2.0 (3-5 trades)", 1.9, 2.1),
        ("2.5 (1-2 trades)", 2.4, 2.6),
        ("3.0 (0 trades)", 2.9, 3.1),
    ]
    print(f"{'Fresh Mult':<20} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8}")
    print("-" * 55)
    for label, lo, hi in fresh_buckets:
        grp = [s for s in sports if lo <= s["fresh_mult"] <= hi]
        if not grp:
            print(f"{label:<20} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{label:<20} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}%")

    # Cross: fresh_mult x entry_price
    print()
    print("  Fresh mult x Entry price (sports):")
    for label, flo, fhi in fresh_buckets:
        grp = [s for s in sports if flo <= s["fresh_mult"] <= fhi]
        if not grp:
            continue
        lo_entry = [s for s in grp if s["effective_entry"] < 0.50]
        hi_entry = [s for s in grp if s["effective_entry"] >= 0.50]
        for elabel, eg in [("<$0.50", lo_entry), (">=$0.50", hi_entry)]:
            if not eg:
                continue
            won = sum(1 for s in eg if s["result"] == "WIN")
            print(f"    {label} + entry {elabel}: {len(eg):>3} signals, "
                  f"{won} won, {won/len(eg)*100:.0f}% WR")
    print()

    # ══════════════════════════════════════════════════════════
    # H2: Entry price as predictor
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  H2: ENTRY PRICE — granular breakdown")
    print("=" * 70)
    # Finer bins around the critical 0.30-0.70 range
    ep_bins = [
        ("$0.00-0.25", 0.00, 0.25),
        ("$0.25-0.35", 0.25, 0.35),
        ("$0.35-0.45", 0.35, 0.45),
        ("$0.45-0.50", 0.45, 0.50),
        ("$0.50-0.52", 0.50, 0.52),
        ("$0.52-0.55", 0.52, 0.55),
        ("$0.55-0.60", 0.55, 0.60),
        ("$0.60-0.70", 0.60, 0.70),
        ("$0.70-0.85", 0.70, 0.85),
        ("$0.85-1.00", 0.85, 1.01),
    ]
    print(f"{'Range':<16} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'$100sim':>9}")
    print("-" * 60)
    for label, lo, hi in ep_bins:
        grp = [s for s in sports if lo <= s["effective_entry"] < hi]
        if not grp:
            print(f"{label:<16} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        # flat $100 sim
        risked = len(grp) * 100
        returned = sum(100 / s["effective_entry"] for s in grp
                       if s["result"] == "WIN" and s["effective_entry"] > 0)
        net_roi = (returned - risked) / risked * 100
        print(f"{label:<16} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}% {net_roi:>+8.1f}%")

    # What win rate do you NEED at each price to break even?
    print()
    print("  Break-even win rates (assuming binary $0/$1 payout):")
    for price in [0.30, 0.40, 0.50, 0.55, 0.60, 0.70, 0.80, 0.90]:
        # Risk = price, payout = 1.0, so BE = price / 1.0 = price
        print(f"    Entry ${price:.2f} -> need {price*100:.0f}% win rate to break even")
    print()

    # ══════════════════════════════════════════════════════════
    # H3: Niche market multiplier vs outcome
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  H3: NICHE MARKET MULTIPLIER — does market thinness predict wins?")
    print("=" * 70)
    niche_buckets = [
        ("1.0 (not niche)", 0.9, 1.1),
        ("1.5 ($25K-50K)", 1.4, 1.6),
        ("2.0 ($10K-25K)", 1.9, 2.1),
        ("2.5 (<$10K)", 2.4, 2.6),
    ]
    print(f"{'Niche Mult':<20} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'AvgEntry':>9}")
    print("-" * 65)
    for label, lo, hi in niche_buckets:
        grp = [s for s in sports if lo <= s["niche_mult"] <= hi]
        if not grp:
            print(f"{label:<20} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        avg_entry = sum(s["effective_entry"] for s in grp) / len(grp)
        print(f"{label:<20} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}% ${avg_entry:>7.2f}")

    # Niche x entry price
    print()
    print("  Niche x Entry price:")
    for label, nlo, nhi in niche_buckets:
        grp = [s for s in sports if nlo <= s["niche_mult"] <= nhi]
        if not grp:
            continue
        contrarian = [s for s in grp if s["effective_entry"] < 0.50]
        favorite = [s for s in grp if s["effective_entry"] >= 0.50]
        for elabel, eg in [("contrarian (<$0.50)", contrarian), ("favorite (>=$0.50)", favorite)]:
            if not eg:
                continue
            won = sum(1 for s in eg if s["result"] == "WIN")
            avg_pnl = sum(s["pnl_pct"] for s in eg) / len(eg)
            print(f"    {label} + {elabel}: {len(eg):>3} signals, "
                  f"{won} won ({won/len(eg)*100:.0f}% WR), avg P&L {avg_pnl:+.1f}%")
    print()

    # ══════════════════════════════════════════════════════════
    # H4: Wallet repeat performance
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  H4: WALLET FRESHNESS — repeat vs one-off wallets")
    print("=" * 70)

    # Count how many alert-level sports signals each wallet has
    wallet_signal_counts: dict[str, int] = {}
    for s in sports:
        wallet_signal_counts[s["wallet"]] = wallet_signal_counts.get(s["wallet"], 0) + 1

    one_off = [s for s in sports if wallet_signal_counts[s["wallet"]] == 1]
    repeat_2 = [s for s in sports if wallet_signal_counts[s["wallet"]] == 2]
    repeat_3p = [s for s in sports if wallet_signal_counts[s["wallet"]] >= 3]

    print(f"{'Wallet Type':<24} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8}")
    print("-" * 55)
    for label, grp in [("One-off (1 signal)", one_off),
                        ("Repeat (2 signals)", repeat_2),
                        ("Repeat (3+ signals)", repeat_3p)]:
        if not grp:
            print(f"{label:<24} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{label:<24} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}%")

    # Now check wallet trade_count from DB (overall Polymarket experience)
    print()
    print("  By wallet overall Polymarket trade count:")
    for s in sports:
        w_row = conn.execute(
            "SELECT trade_count FROM wallets WHERE proxy_wallet = ?",
            (s["wallet"],),
        ).fetchone()
        s["wallet_trades"] = w_row["trade_count"] if w_row else 0

    trade_count_buckets = [
        ("0 trades (brand new)", 0, 1),
        ("1-5 trades", 1, 6),
        ("6-25 trades", 6, 26),
        ("26-100 trades", 26, 101),
        ("100+ trades", 101, 1_000_000),
    ]
    print(f"{'Wallet Experience':<24} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8}")
    print("-" * 55)
    for label, lo, hi in trade_count_buckets:
        grp = [s for s in sports if lo <= s["wallet_trades"] < hi]
        if not grp:
            print(f"{label:<24} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{label:<24} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}%")
    print()

    # ══════════════════════════════════════════════════════════
    # H5: Size anomaly multiplier
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  H5: SIZE ANOMALY MULTIPLIER — does relative size predict wins?")
    print("=" * 70)
    size_buckets = [
        ("1.0 (not outsized)", 0.9, 1.1),
        ("1.5 (2-5% of 24h)", 1.4, 1.6),
        ("2.0 (5-10% of 24h)", 1.9, 2.1),
        ("3.0 (10%+ of 24h)", 2.9, 3.1),
    ]
    print(f"{'Size Mult':<22} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8}")
    print("-" * 55)
    for label, lo, hi in size_buckets:
        grp = [s for s in sports if lo <= s["size_mult"] <= hi]
        if not grp:
            print(f"{label:<22} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{label:<22} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}%")
    print()

    # ══════════════════════════════════════════════════════════
    # COMPOSITE: What if we only follow niche + contrarian?
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  COMPOSITE FILTER TESTS")
    print("=" * 70)
    filters = [
        ("All sports", lambda s: True),
        ("Niche only (mult>=1.5)", lambda s: s["niche_mult"] >= 1.5),
        ("Contrarian only (<$0.50)", lambda s: s["effective_entry"] < 0.50),
        ("Niche + Contrarian", lambda s: s["niche_mult"] >= 1.5 and s["effective_entry"] < 0.50),
        ("Niche + Mid-price ($0.35-0.65)", lambda s: s["niche_mult"] >= 1.5 and 0.35 <= s["effective_entry"] <= 0.65),
        ("Non-fresh (fresh_mult=1)", lambda s: s["fresh_mult"] <= 1.1),
        ("Non-fresh + Contrarian", lambda s: s["fresh_mult"] <= 1.1 and s["effective_entry"] < 0.50),
        ("Repeat wallet (3+ signals)", lambda s: wallet_signal_counts[s["wallet"]] >= 3),
        ("Repeat + Contrarian", lambda s: wallet_signal_counts[s["wallet"]] >= 3 and s["effective_entry"] < 0.50),
        ("Esports only", lambda s: s["league"] in ("LoL", "CS2", "Dota2")),
        ("Non-NBA", lambda s: s["league"] != "NBA"),
    ]
    print(f"{'Filter':<32} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 75)
    for label, fn in filters:
        grp = [s for s in sports if fn(s)]
        if not grp:
            print(f"{label:<32} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        risked = len(grp) * 100
        returned = sum(100 / s["effective_entry"] for s in grp
                       if s["result"] == "WIN" and s["effective_entry"] > 0)
        sim_roi = (returned - risked) / risked * 100
        print(f"{label:<32} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}% {sim_roi:>+7.1f}%")
    print()

    # ══════════════════════════════════════════════════════════
    # DATA GAPS
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  DATA GAPS & LIMITATIONS")
    print("=" * 70)

    # How many sports signals are still open?
    sports_open = [s for s in signals if s["category"] == "Sports" and s["result"] == "OPEN"]
    print(f"Open (unresolved) sports signals: {len(sports_open)}")

    # League distribution of open vs resolved
    open_leagues = {}
    for s in sports_open:
        league = sport_league(s.get("slug", ""))
        open_leagues[league] = open_leagues.get(league, 0) + 1
    if open_leagues:
        print(f"  Open by league: {dict(sorted(open_leagues.items()))}")

    # Wallet profile depth
    shallow = sum(1 for s in sports if s["wallet_trades"] <= 5)
    deep = sum(1 for s in sports if s["wallet_trades"] > 5)
    print("\nWallet profile depth (resolved sports):")
    print(f"  Shallow (<=5 trades): {shallow}")
    print(f"  Deep (>5 trades):     {deep}")

    # Markets with volume data
    no_vol = sum(1 for s in sports if (s.get("volume_24hr") or 0) == 0)
    print(f"\nMissing 24hr volume data: {no_vol}/{len(sports)} signals")

    conn.close()


if __name__ == "__main__":
    main()
