"""Dataset cleaning script: exclude Crypto, reassign Sports, remove duplicates.

Run with --dry-run to preview, without to apply changes.
"""
import sqlite3, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DRY_RUN = "--dry-run" in sys.argv

conn = sqlite3.connect("C:/Users/thoma/AppData/Local/spyhop/spyhop.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()


# ── Helpers ───────────────────────────────────────────────────────

def classify_slug(slug: str) -> str:
    """Classify a market slug as Sports / Crypto / Other."""
    s = (slug or "").lower()
    if any(x in s for x in [
        "nba-","nfl-","nhl-","mlb-","mls-","ncaa","ufc-","mma-","nba_",
        "tennis","atp-","wta-","soccer","football","rugby","cricket",
        "cs2-","lol-","dota","valorant","esport","esports","gaming",
        "boxing","golf","f1-","formula","nascar","wrestling",
        "ucl-","epl-","copa","serie-a","bundesliga","ligue",
        "-total-","spread-","moneyline-","-over-","-under-",
        "sea-","efa-","spl-","ita-","ger-","fra-",  # soccer event prefixes
    ]):
        return "Sports"
    if any(x in s for x in [
        "btc","eth","sol","btcusd","ethusd","bitcoin","ethereum",
        "crypto","xrp","bnb","avax","matic","doge","shib",
        "updown-","up-or-down","-above-","-below-",   # price binary markets
    ]):
        return "Crypto"
    return "Other"


def slug_for_position(pos_id: int) -> str:
    row = cur.execute("""
        SELECT m.slug FROM paper_positions pp
        JOIN trades t ON pp.trade_id = t.id
        LEFT JOIN markets m ON t.condition_id = m.condition_id
        WHERE pp.id = ?
    """, (pos_id,)).fetchone()
    return row["slug"] if row and row["slug"] else ""


# ── Step 1: Load all insider positions ────────────────────────────

cur.execute("""
    SELECT pp.id, pp.thesis, pp.entry_timestamp, pp.condition_id,
           pp.wallet, pp.entry_price, pp.size_usd, pp.market_question,
           m.slug
    FROM paper_positions pp
    JOIN trades t ON pp.trade_id = t.id
    LEFT JOIN markets m ON t.condition_id = m.condition_id
    WHERE pp.thesis = 'insider'
""")
positions = [dict(r) for r in cur.fetchall()]
print(f"Total insider positions: {len(positions)}")

# Classify each
for p in positions:
    p["category"] = classify_slug(p["slug"] or "")

by_cat = defaultdict(list)
for p in positions:
    by_cat[p["category"]].append(p)

print(f"  Sports : {len(by_cat['Sports'])}")
print(f"  Crypto : {len(by_cat['Crypto'])}")
print(f"  Other  : {len(by_cat['Other'])}")


# ── Step 2: Identify Crypto deletions ─────────────────────────────

crypto_ids = [p["id"] for p in by_cat["Crypto"]]
print(f"\n=== Step 1: Delete Crypto positions ({len(crypto_ids)}) ===")
for p in by_cat["Crypto"]:
    print(f"  DELETE #{p['id']} | {p['market_question'][:60]}")

if not DRY_RUN and crypto_ids:
    placeholders = ",".join("?" * len(crypto_ids))
    cur.execute(f"DELETE FROM paper_positions WHERE id IN ({placeholders})", crypto_ids)
    conn.commit()
    print(f"  -> Deleted {len(crypto_ids)} Crypto positions")


# ── Step 3: Reassign Sports to sporty_investor ────────────────────

sports_ids = [p["id"] for p in by_cat["Sports"]]
print(f"\n=== Step 2: Reassign Sports to sporty_investor ({len(sports_ids)}) ===")

# Group by category for a cleaner preview
sports_by_question = defaultdict(int)
for p in by_cat["Sports"]:
    sports_by_question[p["market_question"][:60]] += 1
for q, n in sorted(sports_by_question.items(), key=lambda x: -x[1])[:20]:
    print(f"  [{n}x] {q}")
if len(sports_by_question) > 20:
    print(f"  ... and {len(sports_by_question)-20} more unique markets")

if not DRY_RUN and sports_ids:
    placeholders = ",".join("?" * len(sports_ids))
    cur.execute(
        f"UPDATE paper_positions SET thesis='sporty_investor' WHERE id IN ({placeholders})",
        sports_ids,
    )
    conn.commit()
    print(f"  -> Reassigned {len(sports_ids)} Sports positions to sporty_investor")


# ── Step 4: Find duplicates ────────────────────────────────────────
# Duplicate = same condition_id + same wallet + entry_timestamp within 60s
# Among duplicates, keep the lowest id (first recorded).

print("\n=== Step 3: Identify duplicates ===")
cur.execute("""
    SELECT id, condition_id, wallet, entry_timestamp, entry_price, market_question
    FROM paper_positions
    ORDER BY id ASC
""")
all_pos = [dict(r) for r in cur.fetchall()]

from datetime import datetime, timezone

def parse_ts(ts: str) -> float:
    """Parse ISO timestamp to unix seconds."""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0

# Group by (condition_id, wallet), then within each group find positions
# whose timestamps are within 60s of another — keep earliest, delete rest.
from itertools import combinations

keep_ids = set()
delete_ids = set()

groups = defaultdict(list)
for p in all_pos:
    groups[(p["condition_id"], p["wallet"])].append(p)

dup_groups_shown = 0
for (cid, wallet), grp in groups.items():
    if len(grp) == 1:
        keep_ids.add(grp[0]["id"])
        continue

    # Sort by id (chronological for backfilled positions)
    grp.sort(key=lambda x: x["id"])

    # Greedy dedup: mark each position as a dup if within 60s of an earlier kept position
    kept = []
    for p in grp:
        ts = parse_ts(p["entry_timestamp"])
        is_dup = any(abs(ts - parse_ts(k["entry_timestamp"])) <= 60 for k in kept)
        if is_dup:
            delete_ids.add(p["id"])
        else:
            kept.append(p)
            keep_ids.add(p["id"])

    # Show groups with duplicates
    dups = [p for p in grp if p["id"] in delete_ids]
    if dups and dup_groups_shown < 15:
        q = grp[0]["market_question"][:55]
        print(f"  DUP GROUP: {q}")
        for p in grp:
            tag = "KEEP" if p["id"] in keep_ids else "DEL "
            print(f"    [{tag}] #{p['id']} {p['entry_timestamp'][:19]} @{p['entry_price']:.3f}")
        dup_groups_shown += 1

print(f"\n  Total positions: {len(all_pos)}")
print(f"  Keep: {len(keep_ids)}")
print(f"  Delete (duplicates): {len(delete_ids)}")

if not DRY_RUN and delete_ids:
    placeholders = ",".join("?" * len(delete_ids))
    cur.execute(
        f"DELETE FROM paper_positions WHERE id IN ({placeholders})",
        list(delete_ids),
    )
    conn.commit()
    print(f"  -> Deleted {len(delete_ids)} duplicate positions")


# ── Final summary ─────────────────────────────────────────────────

print("\n=== Final dataset (after cleaning) ===")
cur.execute("""
    SELECT thesis, status, COUNT(*) as n,
           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
           COALESCE(SUM(realized_pnl), 0) as total_pnl
    FROM paper_positions GROUP BY thesis, status ORDER BY thesis, status
""")
for r in cur.fetchall():
    print(f"  {r['thesis']:<20} | {r['status']:<8} | n={r['n']:3d} W:{r['wins']:3d} pnl=${r['total_pnl']:+,.0f}")

if DRY_RUN:
    print("\n(dry run — no changes made)")
else:
    print("\nDone.")

conn.close()
