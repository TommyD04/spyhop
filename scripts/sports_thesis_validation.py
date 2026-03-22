"""Sporty Investor thesis validation.

Scores ALL sports trades (not just alert-level signals) through the proposed
sporty_investor detectors and compares against the current insider composite
scorer baseline.

Key validation questions:
  1. Does the timing gate (pre-game only) hold at N=11K+?
  2. Is the $0.35-0.50 entry price sweet spot real, or small-sample artifact?
  3. Does niche_mult=2.0 ($10K-25K volume) persist at scale?
  4. What should the alert threshold be? 5.0? 6.0? Something else?

Usage:
    cd C:\\Users\\thoma\\Projects\\spyhop
    python scripts/sports_thesis_validation.py
"""

from __future__ import annotations

import io
import json
import math
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from spyhop.config import db_path
from spyhop.storage.db import init_db


# ── Category lookup ──────────────────────────────────────────


def find_category(slug: str, events: list[dict]) -> str:
    """Find category by longest event_slug prefix match."""
    if not slug:
        return "Unknown"
    best = None
    for e in events:
        es = e["event_slug"]
        if slug.startswith(es):
            if best is None or len(es) > len(best["event_slug"]):
                best = e
    return best["primary_tag"] if best else "Unknown"


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


# ── Outcome classification ──────────────────────────────────


def classify(trade: dict) -> None:
    """Classify trade as WIN/LOSS/OPEN based on resolved outcome prices."""
    side = trade["side"]
    oi = trade["outcome_index"] or 0
    ep = trade["price"] or 0

    if side == "SELL":
        trade["effective_entry"] = 1.0 - ep
        eff_oi = 1 - oi
    else:
        trade["effective_entry"] = ep
        eff_oi = oi

    try:
        prices = json.loads(trade.get("outcome_prices") or "[]")
        exit_p = float(prices[eff_oi])
    except (json.JSONDecodeError, IndexError, TypeError, ValueError):
        trade["result"] = "OPEN"
        return

    if exit_p >= 0.99:
        trade["result"] = "WIN"
        ee = trade["effective_entry"]
        trade["pnl_pct"] = (1.0 - ee) / ee * 100 if ee > 0 else 0
    elif exit_p <= 0.01:
        trade["result"] = "LOSS"
        trade["pnl_pct"] = -100.0
    else:
        trade["result"] = "OPEN"


# ── Proposed sporty_investor detectors ──────────────────────


def timing_gate(trade_ts: str, end_date: str | None) -> tuple[float, str]:
    """GATE: 1.0 if pre-game (hours > 0), 0.0 if during/after."""
    if not end_date:
        return 1.0, "no end_date (pass-through)"
    try:
        from datetime import datetime, timezone

        trade_dt = datetime.fromisoformat(trade_ts)
        if trade_dt.tzinfo is None:
            trade_dt = trade_dt.replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        hours_before = (end_dt - trade_dt).total_seconds() / 3600
        if hours_before > 0:
            return 1.0, f"{hours_before:.1f}h before"
        else:
            return 0.0, f"{-hours_before:.1f}h after start"
    except (ValueError, TypeError):
        return 1.0, "unparseable date (pass-through)"


def entry_price_mult(effective_entry: float) -> tuple[float, str]:
    """Contrarian sweet spot: $0.35-0.50 → 2.0x, adjacent → 1.5x, near-certainty → 0.5x."""
    if effective_entry >= 0.85:
        return 0.5, f"near-certainty ${effective_entry:.2f}"
    if 0.35 <= effective_entry <= 0.50:
        return 2.0, f"sweet spot ${effective_entry:.2f}"
    if 0.25 <= effective_entry < 0.35 or 0.50 < effective_entry <= 0.65:
        return 1.5, f"adjacent ${effective_entry:.2f}"
    return 1.0, f"outside ${effective_entry:.2f}"


def niche_nonlinear_mult(volume_24hr: float) -> tuple[float, str]:
    """Non-linear volume sweet spot: $10K-25K → 2.0x, $25K-50K → 1.5x."""
    if 10_000 <= volume_24hr <= 25_000:
        return 2.0, f"sweet spot ${volume_24hr:,.0f}"
    if 25_000 < volume_24hr <= 50_000:
        return 1.5, f"adjacent ${volume_24hr:,.0f}"
    return 1.0, f"outside ${volume_24hr:,.0f}"


def wallet_experience_mult(trade_count: int) -> tuple[float, str]:
    """Inverse of fresh_wallet: experienced wallets are the signal.
    0-2 → 1.0x, 3-5 → 1.3x, 6-25 → 1.8x, 25+ → 1.5x."""
    if 6 <= trade_count <= 25:
        return 1.8, f"sweet spot {trade_count} trades"
    if trade_count > 25:
        return 1.5, f"veteran {trade_count} trades"
    if 3 <= trade_count <= 5:
        return 1.3, f"moderate {trade_count} trades"
    return 1.0, f"novice {trade_count} trades"


def score_sporty(trade: dict) -> None:
    """Apply sporty_investor scoring to a trade dict. Mutates in-place."""
    # Timing gate
    tg_mult, tg_detail = timing_gate(trade["timestamp"], trade.get("end_date"))
    trade["tg_mult"] = tg_mult
    trade["tg_detail"] = tg_detail

    # Entry price
    ep_mult, ep_detail = entry_price_mult(trade["effective_entry"])
    trade["ep_mult"] = ep_mult
    trade["ep_detail"] = ep_detail

    # Niche nonlinear
    vol = trade.get("volume_24hr") or 0
    nn_mult, nn_detail = niche_nonlinear_mult(vol)
    trade["nn_mult"] = nn_mult
    trade["nn_detail"] = nn_detail

    # Wallet experience
    wt = trade.get("wallet_trades") or 0
    we_mult, we_detail = wallet_experience_mult(wt)
    trade["we_mult"] = we_mult
    trade["we_detail"] = we_detail

    # Composite: multiplicative model, same math as scorer.py
    product = tg_mult * ep_mult * nn_mult * we_mult
    # max_product = 1.0 (timing gate) * 2.0 * 2.0 * 1.8 = 7.2
    max_product = 2.0 * 2.0 * 1.8
    normalizer = 10.0 / math.log10(max_product) if max_product > 1.0 else 10.0

    if product <= 1.0:
        trade["sporty_score"] = 0.0
    else:
        trade["sporty_score"] = min(10.0, round(math.log10(product) * normalizer, 1))


# ── Reporting helpers ───────────────────────────────────────


def _report_group(label: str, grp: list[dict], width: int = 32) -> str:
    """Format a single row of win rate / P&L analysis."""
    if not grp:
        return f"{label:<{width}} {'0':>5}"
    won = sum(1 for t in grp if t["result"] == "WIN")
    n = len(grp)
    avg_pnl = sum(t["pnl_pct"] for t in grp) / n
    risked = n * 100
    returned = sum(
        100 / t["effective_entry"]
        for t in grp
        if t["result"] == "WIN" and t["effective_entry"] > 0
    )
    sim_roi = (returned - risked) / risked * 100 if risked > 0 else 0
    return (
        f"{label:<{width}} {n:>5} {won:>5} {n - won:>5} "
        f"{won / n * 100:>5.1f}% {avg_pnl:>+7.1f}% {sim_roi:>+7.1f}%"
    )


def main() -> None:
    conn = init_db(db_path())

    # Fetch all events for category lookup
    events = [dict(r) for r in conn.execute("SELECT * FROM events").fetchall()]

    # Fetch ALL trades with market + wallet data
    rows = conn.execute(
        """SELECT t.id, t.timestamp, t.wallet, t.side, t.usdc_size, t.price,
                  t.condition_id, t.outcome, t.outcome_index,
                  m.outcome_prices, m.slug, m.volume, m.volume_24hr, m.end_date,
                  w.trade_count AS wallet_trades
           FROM trades t
           LEFT JOIN markets m ON t.condition_id = m.condition_id
           LEFT JOIN wallets w ON t.wallet = w.proxy_wallet
           WHERE t.condition_id IS NOT NULL AND t.condition_id != ''"""
    ).fetchall()
    all_trades = [dict(r) for r in rows]

    # Tag with category
    for t in all_trades:
        t["category"] = find_category(t.get("slug") or "", events)

    # Filter to Sports
    sports = [t for t in all_trades if t["category"] == "Sports"]

    print(f"Total trades in DB: {len(all_trades)}")
    print(f"Sports trades: {len(sports)}")

    # Classify all, score all
    for t in sports:
        classify(t)
        # Score regardless of resolution status (need score distribution for all)
        if t.get("effective_entry") is None:
            t["effective_entry"] = t["price"] or 0
        score_sporty(t)
        t["league"] = sport_league(t.get("slug") or "")

    resolved = [t for t in sports if t["result"] in ("WIN", "LOSS")]
    open_trades = [t for t in sports if t["result"] == "OPEN"]
    won_count = sum(1 for t in resolved if t["result"] == "WIN")

    print(f"Resolved: {len(resolved)} ({won_count} W / {len(resolved) - won_count} L)")
    print(f"Open (unresolved): {len(open_trades)}")
    print()

    # ══════════════════════════════════════════════════════════
    # SCORE DISTRIBUTION (all sports trades, including open)
    # ══════════════════════════════════════════════════════════
    print("=" * 70)
    print("  SPORTY SCORE DISTRIBUTION — all sports trades (incl. open)")
    print("=" * 70)

    score_bands = [
        ("0.0 (gated/none)", 0.0, 0.1),
        ("0.1-2.9", 0.1, 3.0),
        ("3.0-4.9", 3.0, 5.0),
        ("5.0-5.9", 5.0, 6.0),
        ("6.0-6.9", 6.0, 7.0),
        ("7.0-7.9", 7.0, 8.0),
        ("8.0-8.9", 8.0, 9.0),
        ("9.0-10.0", 9.0, 10.1),
    ]

    print(f"{'Score Band':<16} {'Total':>6} {'Resolved':>9} {'Open':>6}")
    print("-" * 40)
    for label, lo, hi in score_bands:
        total = [t for t in sports if lo <= t.get("sporty_score", 0) < hi]
        res = [t for t in total if t["result"] in ("WIN", "LOSS")]
        opn = [t for t in total if t["result"] == "OPEN"]
        print(f"{label:<16} {len(total):>6} {len(res):>9} {len(opn):>6}")

    # ══════════════════════════════════════════════════════════
    # WIN RATES BY SCORE BAND (resolved only)
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  WIN RATES BY SPORTY SCORE BAND (resolved only)")
    print("=" * 70)
    print(f"{'Score Band':<16} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 60)
    for label, lo, hi in score_bands:
        grp = [t for t in resolved if lo <= t.get("sporty_score", 0) < hi]
        print(_report_group(label, grp, width=16))

    # ══════════════════════════════════════════════════════════
    # TIMING GATE ANALYSIS
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  DETECTOR 1: TIMING GATE")
    print("=" * 70)

    gated = [t for t in resolved if t.get("tg_mult", 1.0) == 0.0]
    passed = [t for t in resolved if t.get("tg_mult", 1.0) > 0.0]
    no_date = [t for t in resolved if "no end_date" in t.get("tg_detail", "")]

    print(f"Gated (during/after game): {len(gated)}")
    print(f"Passed (pre-game):         {len(passed)}")
    print(f"No end_date (pass-through): {len(no_date)}")

    if gated:
        gated_won = sum(1 for t in gated if t["result"] == "WIN")
        gated_pnl = sum(t["pnl_pct"] for t in gated) / len(gated)
        print(f"  Gated WR:  {gated_won}/{len(gated)} = {gated_won / len(gated) * 100:.1f}%, avg P&L {gated_pnl:+.1f}%")
    if passed:
        passed_won = sum(1 for t in passed if t["result"] == "WIN")
        passed_pnl = sum(t["pnl_pct"] for t in passed) / len(passed)
        print(f"  Passed WR: {passed_won}/{len(passed)} = {passed_won / len(passed) * 100:.1f}%, avg P&L {passed_pnl:+.1f}%")

    # Timing: hours-before distribution for pre-game trades
    print()
    print("  Hours-before distribution (pre-game, resolved):")
    timing_bands = [
        ("0-1h before", 0, 1),
        ("1-4h before", 1, 4),
        ("4-12h before", 4, 12),
        ("12-24h before", 12, 24),
        ("24-72h before", 24, 72),
        ("72h+ before", 72, 100_000),
    ]
    for label, lo, hi in timing_bands:
        grp = []
        for t in passed:
            detail = t.get("tg_detail", "")
            if "h before" in detail:
                try:
                    hrs = float(detail.split("h")[0])
                    if lo <= hrs < hi:
                        grp.append(t)
                except ValueError:
                    pass
        if grp:
            won = sum(1 for t in grp if t["result"] == "WIN")
            print(f"    {label:<18} {len(grp):>5} trades, {won} W ({won / len(grp) * 100:.1f}% WR)")

    # ══════════════════════════════════════════════════════════
    # ENTRY PRICE DETECTOR
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  DETECTOR 2: ENTRY PRICE")
    print("=" * 70)
    ep_groups = [
        ("near-certainty (>=0.85, 0.5x)", lambda t: t.get("ep_mult") == 0.5),
        ("sweet spot (0.35-0.50, 2.0x)", lambda t: t.get("ep_mult") == 2.0),
        ("adjacent (1.5x)", lambda t: t.get("ep_mult") == 1.5),
        ("outside (1.0x)", lambda t: t.get("ep_mult") == 1.0),
    ]
    print(f"{'Entry Price Band':<32} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 78)
    for label, fn in ep_groups:
        grp = [t for t in resolved if fn(t)]
        print(_report_group(label, grp))

    # Finer-grained entry price bins
    print()
    print("  Fine-grained entry price bins:")
    ep_bins = [
        ("$0.00-0.25", 0.00, 0.25),
        ("$0.25-0.35", 0.25, 0.35),
        ("$0.35-0.45", 0.35, 0.45),
        ("$0.45-0.50", 0.45, 0.50),
        ("$0.50-0.55", 0.50, 0.55),
        ("$0.55-0.65", 0.55, 0.65),
        ("$0.65-0.70", 0.65, 0.70),
        ("$0.70-0.85", 0.70, 0.85),
        ("$0.85-1.00", 0.85, 1.01),
    ]
    print(f"  {'Range':<16} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("  " + "-" * 60)
    for label, lo, hi in ep_bins:
        grp = [t for t in resolved if lo <= t["effective_entry"] < hi]
        print("  " + _report_group(label, grp, width=16))

    # ══════════════════════════════════════════════════════════
    # NICHE NONLINEAR DETECTOR
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  DETECTOR 3: NICHE NONLINEAR (24h volume)")
    print("=" * 70)
    nn_groups = [
        ("sweet ($10K-$25K, 2.0x)", lambda t: t.get("nn_mult") == 2.0),
        ("adjacent ($25K-$50K, 1.5x)", lambda t: t.get("nn_mult") == 1.5),
        ("outside (1.0x)", lambda t: t.get("nn_mult") == 1.0),
    ]
    print(f"{'Volume Band':<32} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 78)
    for label, fn in nn_groups:
        grp = [t for t in resolved if fn(t)]
        print(_report_group(label, grp))

    # ══════════════════════════════════════════════════════════
    # WALLET EXPERIENCE DETECTOR
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  DETECTOR 4: WALLET EXPERIENCE")
    print("=" * 70)
    we_groups = [
        ("novice (0-2, 1.0x)", lambda t: t.get("we_mult") == 1.0),
        ("moderate (3-5, 1.3x)", lambda t: t.get("we_mult") == 1.3),
        ("sweet (6-25, 1.8x)", lambda t: t.get("we_mult") == 1.8),
        ("veteran (25+, 1.5x)", lambda t: t.get("we_mult") == 1.5),
    ]
    print(f"{'Experience Band':<32} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 78)
    for label, fn in we_groups:
        grp = [t for t in resolved if fn(t)]
        print(_report_group(label, grp))

    # ══════════════════════════════════════════════════════════
    # BASELINE COMPARISON: Current insider scorer
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  BASELINE: Current Insider Scorer on same Sports trades")
    print("=" * 70)

    # Fetch existing signal scores for these trade IDs
    trade_ids = [t["id"] for t in resolved]
    signal_map: dict[int, float] = {}
    if trade_ids:
        # Batch query in chunks to avoid SQLite variable limit
        for i in range(0, len(trade_ids), 500):
            chunk = trade_ids[i : i + 500]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT trade_id, composite_score FROM signals WHERE trade_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for r in rows:
                signal_map[r["trade_id"]] = r["composite_score"]

    for t in resolved:
        t["insider_score"] = signal_map.get(t["id"], 0.0)

    insider_bands = [
        ("0 (no signal)", 0.0, 0.1),
        ("0.1-4.9", 0.1, 5.0),
        ("5.0-6.9", 5.0, 7.0),
        ("7.0-7.9 (alert)", 7.0, 8.0),
        ("8.0-8.9", 8.0, 9.0),
        ("9.0+ (critical)", 9.0, 10.1),
    ]
    print(f"{'Insider Score':<20} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 65)
    for label, lo, hi in insider_bands:
        grp = [t for t in resolved if lo <= t["insider_score"] < hi]
        print(_report_group(label, grp, width=20))

    # ══════════════════════════════════════════════════════════
    # THRESHOLD ANALYSIS
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  THRESHOLD ANALYSIS: sporty_score >= X (resolved only)")
    print("=" * 70)
    for threshold in [3.0, 4.0, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0]:
        grp = [t for t in resolved if t.get("sporty_score", 0) >= threshold]
        if not grp:
            print(f"  >= {threshold:.1f}: 0 trades")
            continue
        won = sum(1 for t in grp if t["result"] == "WIN")
        risked = len(grp) * 100
        returned = sum(
            100 / t["effective_entry"]
            for t in grp
            if t["result"] == "WIN" and t["effective_entry"] > 0
        )
        sim_roi = (returned - risked) / risked * 100 if risked > 0 else 0
        print(
            f"  >= {threshold:.1f}: {len(grp):>5} trades, "
            f"{won} W / {len(grp) - won} L "
            f"({won / len(grp) * 100:.1f}% WR), "
            f"simROI {sim_roi:+.1f}%"
        )

    # Signal volume at thresholds (all trades, not just resolved)
    print()
    print("  Signal volume at thresholds (ALL sports trades, incl. open):")
    for threshold in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]:
        above = sum(1 for t in sports if t.get("sporty_score", 0) >= threshold)
        print(f"    >= {threshold:.0f}: {above} signals ({above / len(sports) * 100:.1f}% of all sports)")

    # ══════════════════════════════════════════════════════════
    # BY LEAGUE
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  BY LEAGUE (resolved, sporty_score > 0)")
    print("=" * 70)
    scored = [t for t in resolved if t.get("sporty_score", 0) > 0]
    leagues: dict[str, list[dict]] = {}
    for t in scored:
        leagues.setdefault(t["league"], []).append(t)
    print(f"{'League':<12} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgScore':>9} {'AvgPnL%':>8}")
    print("-" * 60)
    for league in sorted(leagues, key=lambda lg: len(leagues[lg]), reverse=True):
        grp = leagues[league]
        won = sum(1 for t in grp if t["result"] == "WIN")
        avg_score = sum(t["sporty_score"] for t in grp) / len(grp)
        avg_pnl = sum(t["pnl_pct"] for t in grp) / len(grp)
        print(
            f"{league:<12} {len(grp):>5} {won:>5} {len(grp) - won:>5} "
            f"{won / len(grp) * 100:>5.1f}% {avg_score:>8.1f} {avg_pnl:>+7.1f}%"
        )

    # ══════════════════════════════════════════════════════════
    # COMPOSITE FILTER TESTS
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  COMPOSITE FILTER TESTS (resolved, various combos)")
    print("=" * 70)
    filters = [
        ("All resolved sports", lambda t: True),
        ("sporty >= 5.0", lambda t: t.get("sporty_score", 0) >= 5.0),
        ("sporty >= 5.0 + pre-game", lambda t: t.get("sporty_score", 0) >= 5.0 and t.get("tg_mult", 0) > 0),
        ("sporty >= 5.0 + sweet entry", lambda t: t.get("sporty_score", 0) >= 5.0 and t.get("ep_mult", 0) >= 2.0),
        ("sporty >= 5.0 + niche", lambda t: t.get("sporty_score", 0) >= 5.0 and t.get("nn_mult", 0) >= 1.5),
        ("sporty >= 5.0 + experienced", lambda t: t.get("sporty_score", 0) >= 5.0 and t.get("we_mult", 0) >= 1.3),
        ("sporty >= 6.0", lambda t: t.get("sporty_score", 0) >= 6.0),
        ("sporty >= 7.0", lambda t: t.get("sporty_score", 0) >= 7.0),
        ("insider >= 7.0 (baseline)", lambda t: t["insider_score"] >= 7.0),
    ]
    print(f"{'Filter':<34} {'N':>5} {'Won':>5} {'Lost':>5} {'Win%':>6} {'AvgPnL%':>8} {'SimROI':>8}")
    print("-" * 80)
    for label, fn in filters:
        grp = [t for t in resolved if fn(t)]
        print(_report_group(label, grp, width=34))

    # ══════════════════════════════════════════════════════════
    # TOP 20 HIGHEST SPORTY INVESTOR SIGNALS
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  TOP 20 SPORTY INVESTOR SIGNALS (resolved)")
    print("=" * 70)
    top = sorted(resolved, key=lambda t: t.get("sporty_score", 0), reverse=True)[:20]
    print(
        f"{'Score':>5} {'Res':>4} {'TG':>4} {'EP':>4} {'NN':>4} {'WE':>4} "
        f"{'Entry':>6} {'Size':>9} {'League':<8} {'Market'}"
    )
    print("-" * 100)
    for t in top:
        result_str = " W" if t["result"] == "WIN" else " L"
        question = (t.get("market_question") or t["condition_id"][:20] or "?")[:35]
        print(
            f"{t.get('sporty_score', 0):>5.1f} {result_str:>4} "
            f"{t.get('tg_mult', 0):>4.1f} {t.get('ep_mult', 0):>4.1f} "
            f"{t.get('nn_mult', 0):>4.1f} {t.get('we_mult', 0):>4.1f} "
            f"${t['effective_entry']:>4.2f} "
            f"${t['usdc_size']:>8,.0f} "
            f"{t['league']:<8} {question}"
        )

    # ══════════════════════════════════════════════════════════
    # DATA GAPS
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("  DATA GAPS & COVERAGE")
    print("=" * 70)

    no_end = sum(1 for t in sports if not t.get("end_date"))
    no_vol = sum(1 for t in sports if (t.get("volume_24hr") or 0) == 0)
    no_wallet = sum(1 for t in sports if (t.get("wallet_trades") or 0) == 0 and t.get("wallet_trades") is not None)

    print(f"Missing end_date (timing gate inert): {no_end}/{len(sports)} ({no_end / len(sports) * 100:.1f}%)")
    print(f"Missing 24h volume (niche inert):     {no_vol}/{len(sports)} ({no_vol / len(sports) * 100:.1f}%)")
    print(f"Zero wallet trades:                   {no_wallet}/{len(sports)}")

    # Open by league
    open_leagues: dict[str, int] = {}
    for t in open_trades:
        league = t.get("league", "?")
        open_leagues[league] = open_leagues.get(league, 0) + 1
    if open_leagues:
        print(f"\nOpen (unresolved) by league: {dict(sorted(open_leagues.items(), key=lambda x: -x[1]))}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
