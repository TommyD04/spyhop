"""Part 2: 2D breakdown, category proxy, and focus combo."""
import sqlite3, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

conn = sqlite3.connect("C:/Users/thoma/AppData/Local/spyhop/spyhop.db")
conn.row_factory = sqlite3.Row

# 2D: niche_mult x entry_price
print("=== niche x entry price 2D (insider, B1-filtered) ===")
rows = conn.execute("""
    SELECT s.niche_mult, pp.entry_price, pp.realized_pnl
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
""").fetchall()

grid = defaultdict(list)
for r in rows:
    nm = r["niche_mult"]
    e = r["entry_price"]
    if e < 0.30:   ep = "<0.30"
    elif e < 0.50: ep = "0.30-0.50"
    elif e < 0.70: ep = "0.50-0.70"
    else:          ep = "0.70-0.85"
    grid[(nm, ep)].append(r["realized_pnl"])

for (nm, ep), pnls in sorted(grid.items(), reverse=True):
    n = len(pnls)
    w = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    ae_approx = ""
    print(f"  niche={nm:.1f} {ep:12s}: n={n:3d} W:{w:3d} ({w/n*100:.0f}%) total=${total:+,.0f}")

# Category via slug pattern matching
print("\n=== insider B1-filtered: category via slug pattern ===")
rows2 = conn.execute("""
    SELECT m.slug, pp.entry_price, pp.realized_pnl
    FROM paper_positions pp
    JOIN trades t ON pp.trade_id=t.id
    JOIN markets m ON t.condition_id=m.condition_id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
""").fetchall()

slug_buckets = defaultdict(list)
for r in rows2:
    slug = (r["slug"] or "").lower()
    if any(x in slug for x in ["nba","nfl","mlb","nhl","soccer","tennis","ufc","mma","esport","cs2","lol-","dota","valorant","boxing","cricket"]):
        cat = "Sports"
    elif any(x in slug for x in ["trump","biden","election","president","congress","senate","vote","democrat","republican","harris","zelensky","ukraine","tariff","nato"]):
        cat = "Politics"
    elif any(x in slug for x in ["btc","eth","sol","crypto","bitcoin","ethereum","xrp"]):
        cat = "Crypto"
    elif any(x in slug for x in ["fed","rate","gdp","inflation","stock","s-and-p","nasdaq","dow","economy"]):
        cat = "Finance"
    else:
        cat = "Other"
    slug_buckets[cat].append({"pnl": r["realized_pnl"], "entry": r["entry_price"]})

for cat, ps in sorted(slug_buckets.items()):
    n = len(ps)
    w = sum(1 for p in ps if p["pnl"] > 0)
    total = sum(p["pnl"] for p in ps)
    ae = sum(p["entry"] for p in ps) / n
    ev = w/n - ae
    print(f"  {cat:<12}: n={n:3d} W:{w:3d} ({w/n*100:.0f}%) EV={ev*100:+.0f}pp total=${total:+,.0f}")

# The niche=2.0 AND entry 0.30-0.50 focus combo
print("\n=== FOCUS COMBO: niche=2.0 AND entry 0.30-0.50 ===")
ps = conn.execute("""
    SELECT pp.entry_price, pp.realized_pnl, pp.market_question, pp.score_at_entry,
           s.fresh_mult, s.niche_detail
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED'
      AND s.niche_mult=2.0 AND pp.entry_price>=0.30 AND pp.entry_price<0.50
    ORDER BY pp.realized_pnl DESC
""").fetchall()
if ps:
    wins = sum(1 for p in ps if p["realized_pnl"] > 0)
    total = sum(p["realized_pnl"] for p in ps)
    ae = sum(p["entry_price"] for p in ps) / len(ps)
    print(f"  n={len(ps)} W:{wins} ({wins/len(ps)*100:.0f}%) EV={(wins/len(ps)-ae)*100:+.0f}pp total=${total:+,.0f}")
    for p in ps:
        r = "W" if p["realized_pnl"] > 0 else "L"
        print(f"  [{r}] {p['score_at_entry']:.1f} fresh={p['fresh_mult']:.1f} @{p['entry_price']:.3f} ${p['realized_pnl']:+,.0f} | {p['market_question'][:62]}")
else:
    print("  No positions found")

# Also: what are the winning positions in 0.30-0.50 entry regardless of niche?
print("\n=== entry 0.30-0.50 positions (all niche, insider B1) — sorted by niche ===")
ps2 = conn.execute("""
    SELECT pp.entry_price, pp.realized_pnl, pp.market_question, pp.score_at_entry,
           s.niche_mult, s.fresh_mult, s.niche_detail
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED'
      AND pp.entry_price>=0.30 AND pp.entry_price<0.50
    ORDER BY s.niche_mult DESC, pp.realized_pnl DESC
""").fetchall()
for p in ps2:
    r = "W" if p["realized_pnl"] > 0 else "L"
    print(f"  [{r}] niche={p['niche_mult']:.1f} fresh={p['fresh_mult']:.1f} {p['score_at_entry']:.1f} @{p['entry_price']:.3f} ${p['realized_pnl']:+,.0f} | {p['market_question'][:55]}")

conn.close()
