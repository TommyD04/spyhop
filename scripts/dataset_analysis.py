"""One-off dataset analysis for hypothesis generation."""
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

db_path = "C:/Users/thoma/AppData/Local/spyhop/spyhop.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

BUCKETS = [("<0.15",0,0.15),("0.15-0.30",0.15,0.30),("0.30-0.50",0.30,0.50),
           ("0.50-0.70",0.50,0.70),("0.70-0.85",0.70,0.85),(">0.85",0.85,2.0)]

def ev_row(ps):
    if not ps: return None
    wins = sum(1 for p in ps if p["realized_pnl"] > 0)
    total = sum(p["realized_pnl"] for p in ps)
    ae = sum(p["entry_price"] for p in ps) / len(ps)
    ev = wins / len(ps) - ae
    return len(ps), wins, wins/len(ps)*100, ev*100, total, ae

print("=== DATASET OVERVIEW ===")
cur.execute("""
    SELECT thesis, status, COUNT(*) as n,
           SUM(CASE WHEN realized_pnl>0 THEN 1 ELSE 0 END) as wins,
           SUM(realized_pnl) as total,
           MIN(entry_timestamp) as t0, MAX(entry_timestamp) as t1
    FROM paper_positions GROUP BY thesis, status ORDER BY thesis, status
""")
for r in cur.fetchall():
    total = r['total'] or 0
    print(f"  {r['thesis']} | {r['status']} | n={r['n']} W:{r['wins']} pnl=${total:+,.0f} | {r['t0'][:10]}->{r['t1'][:10]}")

# INSIDER: entry price buckets
print("\n=== INSIDER resolved: entry price buckets ===")
cur.execute("SELECT entry_price, realized_pnl FROM paper_positions WHERE thesis='insider' AND status='RESOLVED'")
rows = [dict(r) for r in cur.fetchall()]
for lbl,lo,hi in BUCKETS:
    ps = [r for r in rows if lo <= r["entry_price"] < hi]
    if not ps: continue
    n,w,wr,ev,total,ae = ev_row(ps)
    print(f"  {lbl:12s}: n={n:3d} W:{w:3d} ({wr:.0f}%) EV={ev:+.0f}pp total=${total:+,.0f} avg_entry={ae:.3f}")

# INSIDER: B1 filtered
print("\n=== INSIDER resolved: B1-filtered (entry<0.85) ===")
b1 = [r for r in rows if r["entry_price"] < 0.85]
if b1:
    n,w,wr,ev,total,ae = ev_row(b1)
    print(f"  n={n} W:{w} ({wr:.0f}%) EV={ev:+.0f}pp total=${total:+,.0f} avg_entry={ae:.3f}")

# INSIDER: B1-filtered score bands
print("\n=== INSIDER resolved: B1-filtered score bands ===")
cur.execute("""
    SELECT CAST(score_at_entry AS INTEGER) as band, COUNT(*) as n,
           SUM(CASE WHEN realized_pnl>0 THEN 1 ELSE 0 END) as wins,
           SUM(realized_pnl) as total, AVG(entry_price) as ae
    FROM paper_positions WHERE thesis='insider' AND status='RESOLVED' AND entry_price<0.85
    GROUP BY band ORDER BY band DESC
""")
for r in cur.fetchall():
    ev = r["wins"]/r["n"] - r["ae"]
    print(f"  {r['band']}-{r['band']+1}: n={r['n']:3d} W:{r['wins']:3d} ({r['wins']/r['n']*100:.0f}%) EV={ev*100:+.0f}pp total=${r['total']:+,.0f} avg_entry={r['ae']:.3f}")

# INSIDER: fresh_mult
print("\n=== INSIDER: fresh_mult vs outcome (entry<0.85) ===")
cur.execute("""
    SELECT s.fresh_mult, COUNT(*) as n,
           SUM(CASE WHEN pp.realized_pnl>0 THEN 1 ELSE 0 END) as wins,
           SUM(pp.realized_pnl) as total, AVG(pp.entry_price) as ae
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
    GROUP BY s.fresh_mult ORDER BY s.fresh_mult DESC
""")
for r in cur.fetchall():
    ev = r["wins"]/r["n"] - r["ae"]
    print(f"  fresh={r['fresh_mult']:.1f}x: n={r['n']:3d} W:{r['wins']:3d} ({r['wins']/r['n']*100:.0f}%) EV={ev*100:+.0f}pp total=${r['total']:+,.0f}")

# INSIDER: niche_mult
print("\n=== INSIDER: niche_mult vs outcome (entry<0.85) ===")
cur.execute("""
    SELECT s.niche_mult, COUNT(*) as n,
           SUM(CASE WHEN pp.realized_pnl>0 THEN 1 ELSE 0 END) as wins,
           SUM(pp.realized_pnl) as total, AVG(pp.entry_price) as ae
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
    GROUP BY s.niche_mult ORDER BY s.niche_mult DESC
""")
for r in cur.fetchall():
    ev = r["wins"]/r["n"] - r["ae"]
    print(f"  niche={r['niche_mult']:.1f}x: n={r['n']:3d} W:{r['wins']:3d} ({r['wins']/r['n']*100:.0f}%) EV={ev*100:+.0f}pp total=${r['total']:+,.0f}")

# INSIDER: size_mult
print("\n=== INSIDER: size_mult vs outcome (entry<0.85) ===")
cur.execute("""
    SELECT s.size_mult, COUNT(*) as n,
           SUM(CASE WHEN pp.realized_pnl>0 THEN 1 ELSE 0 END) as wins,
           SUM(pp.realized_pnl) as total, AVG(pp.entry_price) as ae
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
    GROUP BY s.size_mult ORDER BY s.size_mult DESC
""")
for r in cur.fetchall():
    ev = r["wins"]/r["n"] - r["ae"]
    print(f"  size={r['size_mult']:.1f}x: n={r['n']:3d} W:{r['wins']:3d} ({r['wins']/r['n']*100:.0f}%) EV={ev*100:+.0f}pp total=${r['total']:+,.0f}")

# INSIDER: category
print("\n=== INSIDER: category breakdown (entry<0.85) ===")
cur.execute("""
    SELECT COALESCE(e.primary_tag,'Unknown') as cat, COUNT(*) as n,
           SUM(CASE WHEN pp.realized_pnl>0 THEN 1 ELSE 0 END) as wins,
           SUM(pp.realized_pnl) as total, AVG(pp.entry_price) as ae
    FROM paper_positions pp
    JOIN trades t ON pp.trade_id=t.id
    LEFT JOIN events e ON t.condition_id=e.condition_id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
    GROUP BY cat ORDER BY n DESC
""")
for r in cur.fetchall():
    ev = r["wins"]/r["n"] - r["ae"]
    print(f"  {r['cat']:<25} n={r['n']:3d} W:{r['wins']:3d} ({r['wins']/r['n']*100:.0f}%) EV={ev*100:+.0f}pp total=${r['total']:+,.0f}")

# INSIDER: 2D niche x entry price
print("\n=== INSIDER: niche_mult x entry_price bucket (B1 filtered) ===")
cur.execute("""
    SELECT s.niche_mult, pp.entry_price, pp.realized_pnl
    FROM paper_positions pp JOIN signals s ON pp.signal_id=s.id
    WHERE pp.thesis='insider' AND pp.status='RESOLVED' AND pp.entry_price<0.85
""")
nd_rows = [dict(r) for r in cur.fetchall()]
for nm in sorted(set(r["niche_mult"] for r in nd_rows), reverse=True):
    for lbl,lo,hi in BUCKETS:
        ps = [r for r in nd_rows if r["niche_mult"]==nm and lo<=r["entry_price"]<hi]
        if not ps: continue
        n,w,wr,ev,total,ae = ev_row(ps)
        print(f"  niche={nm:.1f} {lbl:12s}: n={n:3d} W:{w:3d} ({wr:.0f}%) EV={ev:+.0f}pp total=${total:+,.0f}")

# SPORTY: entry price buckets
print("\n=== SPORTY resolved: entry price buckets ===")
cur.execute("SELECT entry_price, realized_pnl FROM paper_positions WHERE thesis='sporty_investor' AND status='RESOLVED'")
srows = [dict(r) for r in cur.fetchall()]
for lbl,lo,hi in BUCKETS:
    ps = [r for r in srows if lo <= r["entry_price"] < hi]
    if not ps: continue
    n,w,wr,ev,total,ae = ev_row(ps)
    print(f"  {lbl:12s}: n={n:3d} W:{w:3d} ({wr:.0f}%) EV={ev:+.0f}pp total=${total:+,.0f}")

# SPORTY: post-reset
print("\n=== SPORTY: post-reset (2026-03-24+) resolved ===")
cur.execute("""
    SELECT entry_price, realized_pnl, score_at_entry, market_question
    FROM paper_positions WHERE thesis='sporty_investor' AND status='RESOLVED' AND entry_timestamp>='2026-03-24'
""")
post = [dict(r) for r in cur.fetchall()]
if post:
    n,w,wr,ev,total,ae = ev_row(post)
    print(f"  n={n} W:{w} ({wr:.0f}%) EV={ev:+.0f}pp total=${total:+,.0f}")
    for p in sorted(post, key=lambda x: x["realized_pnl"], reverse=True):
        r = "W" if p["realized_pnl"]>0 else "L"
        print(f"    [{r}] {p['score_at_entry']:.1f}s @{p['entry_price']:.2f} ${p['realized_pnl']:+,.0f} | {p['market_question'][:55]}")
else:
    print("  None yet")

# TOP WINS / LOSSES
print("\n=== TOP 10 WINS ===")
cur.execute("""
    SELECT thesis, score_at_entry, entry_price, realized_pnl, market_question
    FROM paper_positions WHERE status='RESOLVED' AND realized_pnl>0
    ORDER BY realized_pnl DESC LIMIT 10
""")
for r in cur.fetchall():
    s = "s" if r["thesis"]=="sporty_investor" else ""
    print(f"  +${r['realized_pnl']:>8,.0f} {r['thesis'][:2].upper()} {r['score_at_entry']:.1f}{s} @{r['entry_price']:.3f} | {r['market_question'][:55]}")

print("\n=== TOP 10 LOSSES ===")
cur.execute("""
    SELECT thesis, score_at_entry, entry_price, realized_pnl, market_question
    FROM paper_positions WHERE status='RESOLVED' AND realized_pnl<0
    ORDER BY realized_pnl ASC LIMIT 10
""")
for r in cur.fetchall():
    s = "s" if r["thesis"]=="sporty_investor" else ""
    print(f"  ${r['realized_pnl']:>9,.0f} {r['thesis'][:2].upper()} {r['score_at_entry']:.1f}{s} @{r['entry_price']:.3f} | {r['market_question'][:55]}")

conn.close()
