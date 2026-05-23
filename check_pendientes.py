"""Lista las aplicaciones pendientes en la DB."""
import sqlite3
from pathlib import Path

db = Path(__file__).parent / "data" / "jobagent.db"
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT title, company, portal, relevance_score, url, created_at
    FROM applications
    WHERE status='pendiente'
    ORDER BY relevance_score DESC
""").fetchall()

print(f"\n=== {len(rows)} aplicaciones pendientes ===\n")
for i, r in enumerate(rows, 1):
    score = r["relevance_score"] or 0
    title = (r["title"] or "")[:55]
    company = (r["company"] or "")[:25]
    portal = r["portal"] or "?"
    print(f"{i:2d}. [{score:.0%}] {title} @ {company} ({portal})")

# Stats por portal
print("\n=== Por portal ===")
by_portal = conn.execute("""
    SELECT portal, COUNT(*) as n, AVG(relevance_score) as avg_score
    FROM applications
    WHERE status='pendiente'
    GROUP BY portal
""").fetchall()
for r in by_portal:
    print(f"  {r['portal']:15s}: {r['n']} (score promedio: {r['avg_score']:.0%})")
