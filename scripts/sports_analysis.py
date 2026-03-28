"""Deep-dive: Is there money in the sports signals?

Slices resolved sports signals by bet type, entry price, score band,
league, trade size, and wallet performance.

Usage:
    cd C:\\Users\\thoma\\Projects\\spyhop
    python scripts/sports_analysis.py
"""

from __future__ import annotations

import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from spyhop.config import db_path
from spyhop.storage.db import init_db


def classify(sig: dict) -> None:
    """Add result, effective_entry, exit_price, pnl_pct to signal dict."""
    side = sig["side"]
    oi = sig["outcome_index"] or 0
    ep = sig["entry_price"] or 0
    if side == "SELL":
        sig["effective_oi"] = 1 - oi
        sig["effective_entry"] = 1.0 - ep
    else:
        sig["effective_oi"] = oi
        sig["effective_entry"] = ep
    try:
        prices = json.loads(sig["outcome_prices"] or "[]")
        exit_p = float(prices[sig["effective_oi"]])
    except (json.JSONDecodeError, IndexError, TypeError, ValueError):
        sig["result"], sig["exit_price"], sig["pnl_pct"] = "OPEN", 0, 0
        return
    sig["exit_price"] = exit_p
    ee = sig["effective_entry"]
    if exit_p >= 0.99:
        sig["result"] = "WIN"
        sig["pnl_pct"] = (1.0 - ee) / ee * 100 if ee > 0 else 0
    elif exit_p <= 0.01:
        sig["result"] = "LOSS"
        sig["pnl_pct"] = -100.0
    else:
        sig["result"] = "OPEN"
        sig["pnl_pct"] = 0


def bet_type(q: str) -> str:
    q = (q or "").lower()
    if "o/u" in q or "total" in q:
        return "Over/Under"
    if "spread" in q:
        return "Spread"
    if "handicap" in q:
        return "Handicap"
    if "will" in q and "win" in q:
        return "Moneyline"
    if " vs " in q or " vs. " in q:
        return "Moneyline"
    return "Other"


def sport_league(q: str, slug: str) -> str:
    slug = (slug or "").lower()
    q = (q or "").lower()
    if slug.startswith("nba-") or "nba" in q:
        return "NBA"
    if slug.startswith("nhl-"):
        return "NHL"
    if slug.startswith("cbb-"):
        return "CBB"
    if slug.startswith("lol-") or "lol:" in q:
        return "LoL"
    if slug.startswith("cs2-"):
        return "CS2"
    if slug.startswith("dota2-"):
        return "Dota2"
    if slug.startswith("epl-") or slug.startswith("ucl-"):
        return "Soccer"
    if slug.startswith("atp-"):
        return "Tennis"
    if slug.startswith("elc-") or slug.startswith("itsb-"):
        return "Soccer"
    return "Other"


def main() -> None:
    conn = init_db(db_path())

    rows = conn.execute(
        """SELECT s.composite_score, t.side, t.price AS entry_price,
                  t.condition_id, t.outcome_index, t.market_question,
                  t.usdc_size, t.wallet, s.timestamp AS signal_ts,
                  m.outcome_prices, m.slug, m.volume, m.volume_24hr
           FROM signals s
           JOIN trades t ON s.trade_id = t.id
           LEFT JOIN markets m ON t.condition_id = m.condition_id
           WHERE s.is_alert = 1
             AND t.condition_id IS NOT NULL AND t.condition_id != ''
           ORDER BY s.composite_score DESC"""
    ).fetchall()

    signals = [dict(r) for r in rows]

    # Category lookup
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

    sports = [s for s in signals if s["category"] == "Sports" and s["result"] in ("WIN", "LOSS")]

    won_total = sum(1 for s in sports if s["result"] == "WIN")
    print(f"Resolved Sports signals: {len(sports)}")
    print(f"Won: {won_total}, Lost: {len(sports) - won_total}")
    print(f"Win rate: {won_total / len(sports) * 100:.1f}%")
    print()

    # Enrich
    for s in sports:
        s["bet_type"] = bet_type(s["market_question"])
        s["league"] = sport_league(s["market_question"], s.get("slug", ""))

    bands = [("7.0-7.9", 7.0, 8.0), ("8.0-8.9", 8.0, 9.0), ("9.0-10.0", 9.0, 10.01)]

    # ── By bet type ──────────────────────────────────────────
    print("=" * 65)
    print("  BY BET TYPE")
    print("=" * 65)
    print(f"{'Type':<16} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>9} {'AvgPnL%':>8}")
    print("-" * 65)
    for bt in sorted(set(s["bet_type"] for s in sports)):
        grp = [s for s in sports if s["bet_type"] == bt]
        won = [s for s in grp if s["result"] == "WIN"]
        avg_entry = sum(s["effective_entry"] for s in grp) / len(grp)
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{bt:<16} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% ${avg_entry:>7.2f} {avg_pnl:>+7.1f}%")
    print()

    # ── By entry price ───────────────────────────────────────
    print("=" * 65)
    print("  BY ENTRY PRICE (Sports only)")
    print("=" * 65)
    price_bands = [
        ("$0.00-0.30", 0.00, 0.30),
        ("$0.30-0.50", 0.30, 0.50),
        ("$0.50-0.55", 0.50, 0.55),
        ("$0.55-0.70", 0.55, 0.70),
        ("$0.70-0.85", 0.70, 0.85),
        ("$0.85-1.00", 0.85, 1.01),
    ]
    print(f"{'Range':<16} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8}")
    print("-" * 55)
    for label, lo, hi in price_bands:
        grp = [s for s in sports if lo <= s["effective_entry"] < hi]
        if not grp:
            print(f"{label:<16} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{label:<16} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% {avg_pnl:>+7.1f}%")
    print()

    # ── By score band ────────────────────────────────────────
    print("=" * 65)
    print("  BY SCORE BAND (Sports only)")
    print("=" * 65)
    print(f"{'Band':<12} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>9} {'AvgPnL%':>8}")
    print("-" * 55)
    for label, lo, hi in bands:
        grp = [s for s in sports if lo <= s["composite_score"] < hi]
        if not grp:
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_entry = sum(s["effective_entry"] for s in grp) / len(grp)
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{label:<12} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% ${avg_entry:>7.2f} {avg_pnl:>+7.1f}%")
    print()

    # ── Flat-bet simulation ──────────────────────────────────
    print("=" * 65)
    print("  FLAT $100 BET SIMULATION (Sports)")
    print("=" * 65)
    total_risked = len(sports) * 100
    total_returned = sum(
        100 / s["effective_entry"]
        for s in sports
        if s["result"] == "WIN" and s["effective_entry"] > 0
    )
    net = total_returned - total_risked
    print(f"Signals:     {len(sports)}")
    print(f"Risked:      ${total_risked:,.0f}")
    print(f"Returned:    ${total_returned:,.0f}")
    print(f"Net P&L:     ${net:>+,.0f}")
    print(f"ROI:         {net/total_risked*100:>+.1f}%")
    print()

    print("  By score band:")
    for label, lo, hi in bands:
        grp = [s for s in sports if lo <= s["composite_score"] < hi]
        if not grp:
            continue
        risked = len(grp) * 100
        returned = sum(
            100 / s["effective_entry"]
            for s in grp
            if s["result"] == "WIN" and s["effective_entry"] > 0
        )
        n = returned - risked
        print(f"  {label}: risked ${risked:,}, returned ${returned:,.0f}, "
              f"net ${n:>+,.0f} ({n/risked*100:>+.1f}% ROI)")
    print()

    # ── By league ────────────────────────────────────────────
    print("=" * 65)
    print("  BY LEAGUE")
    print("=" * 65)
    print(f"{'League':<10} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>9} {'AvgPnL%':>8}")
    print("-" * 55)
    for league in sorted(set(s["league"] for s in sports)):
        grp = [s for s in sports if s["league"] == league]
        won = [s for s in grp if s["result"] == "WIN"]
        avg_entry = sum(s["effective_entry"] for s in grp) / len(grp)
        avg_pnl = sum(s["pnl_pct"] for s in grp) / len(grp)
        print(f"{league:<10} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% ${avg_entry:>7.2f} {avg_pnl:>+7.1f}%")
    print()

    # ── By trade size ────────────────────────────────────────
    print("=" * 65)
    print("  BY TRADE SIZE (USD)")
    print("=" * 65)
    size_bands = [
        ("$10K-25K", 10000, 25000),
        ("$25K-50K", 25000, 50000),
        ("$50K-100K", 50000, 100000),
        ("$100K+", 100000, 1e9),
    ]
    print(f"{'Size':<14} {'N':>4} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgEntry':>9}")
    print("-" * 50)
    for label, lo, hi in size_bands:
        grp = [s for s in sports if lo <= s["usdc_size"] < hi]
        if not grp:
            print(f"{label:<14} {'0':>4}")
            continue
        won = [s for s in grp if s["result"] == "WIN"]
        avg_entry = sum(s["effective_entry"] for s in grp) / len(grp)
        print(f"{label:<14} {len(grp):>4} {len(won):>5} {len(grp)-len(won):>5} "
              f"{len(won)/len(grp)*100:>5.1f}% ${avg_entry:>7.2f}")
    print()

    # ── Signal concentration ─────────────────────────────────
    cid_stats: dict[str, dict] = {}
    for s in sports:
        cid = s["condition_id"]
        if cid not in cid_stats:
            cid_stats[cid] = {"total": 0, "won": 0, "question": s["market_question"]}
        cid_stats[cid]["total"] += 1
        if s["result"] == "WIN":
            cid_stats[cid]["won"] += 1

    print("=" * 65)
    print("  SIGNAL CONCENTRATION")
    print("=" * 65)
    print(f"Unique markets:          {len(cid_stats)}")
    print(f"Avg signals/market:      {len(sports)/len(cid_stats):.1f}")
    multi = {k: v for k, v in cid_stats.items() if v["total"] > 1}
    print(f"Markets with 2+ signals: {len(multi)}")

    # Deduplicated: majority vote per market
    dedup_won = sum(1 for v in cid_stats.values() if v["won"] > v["total"] / 2)
    dedup_lost = len(cid_stats) - dedup_won
    dedup_wr = dedup_won / len(cid_stats) * 100
    print(f"\nDeduped (1 bet/market):  {len(cid_stats)} markets")
    print(f"  Won: {dedup_won}, Lost: {dedup_lost}")
    print(f"  Win rate: {dedup_wr:.1f}%")
    print()

    # ── Wallet performance ───────────────────────────────────
    wallet_stats: dict[str, dict] = {}
    for s in sports:
        w = s["wallet"][:10]
        if w not in wallet_stats:
            wallet_stats[w] = {"won": 0, "lost": 0, "full": s["wallet"]}
        if s["result"] == "WIN":
            wallet_stats[w]["won"] += 1
        else:
            wallet_stats[w]["lost"] += 1

    repeat_wallets = {k: v for k, v in wallet_stats.items() if v["won"] + v["lost"] >= 3}
    if repeat_wallets:
        print("=" * 65)
        print("  WALLET PERFORMANCE (3+ resolved sports signals)")
        print("=" * 65)
        print(f"{'Wallet':<12} {'Won':>5} {'Lost':>5} {'Total':>5} {'Win%':>6}")
        print("-" * 40)
        for w, st in sorted(repeat_wallets.items(), key=lambda x: x[1]["won"]+x[1]["lost"], reverse=True):
            total = st["won"] + st["lost"]
            print(f"{w:<12} {st['won']:>5} {st['lost']:>5} {total:>5} "
                  f"{st['won']/total*100:>5.1f}%")
    else:
        print("No wallets with 3+ resolved sports signals.")

    conn.close()


if __name__ == "__main__":
    main()
