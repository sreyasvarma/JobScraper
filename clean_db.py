"""
clean_db.py — removes junk entries from jobs.db that were scraped before
the title filter was added. Run once: python clean_db.py
"""
import sqlite3
import re

DB_PATH = "jobs.db"

JUNK_PATTERNS = [
    r"^(careers?|jobs?|work with us|join us|our team|life at|working at)$",
    r"^(home|about|contact|privacy|terms|cookies?|sitemap|faq|help|support)$",
    r"^(sign in|log in|login|register|apply now|learn more|read more|view all)$",
    r"^(opens? in a new (window|tab))$",
    r"(e-verify|accommodation|disability|equal opportunity|eeo|affirmative action)",
    r"(drug.free|background check|reasonable accommodation)",
    r"^(search|filter|sort|results?|page \d+|\d+ results?)$",
    r"(cookie|privacy policy|terms of (service|use)|legal)",
    r"^(follow us|connect with|share|tweet|linkedin|facebook|instagram|twitter)$",
    r"(work-life balance|benefits?|perks?|culture|values?|mission|vision)",
    r"^[\d\s\-\(\)\+\.]{5,}$",
    r"^.{0,3}$",
    r"^.{150,}$",
]

JUNK_URL_PATTERNS = [
    "/about", "/culture", "/benefits", "/perks", "/team", "/blog",
    "/news", "/press", "/legal", "/privacy", "/terms", "/cookie",
    "/contact", "/help", "/support", "/faq", "/sitemap",
    "facebook.com", "twitter.com", "linkedin.com", "instagram.com",
]

def is_junk(title: str, url: str) -> bool:
    t = (title or "").strip().lower()
    for p in JUNK_PATTERNS:
        if re.search(p, t, re.IGNORECASE):
            return True
    u = (url or "").lower()
    for p in JUNK_URL_PATTERNS:
        if p in u:
            return True
    return False

conn = sqlite3.connect(DB_PATH)
rows = conn.execute("SELECT id, title, url FROM jobs").fetchall()

junk_ids = [row[0] for row in rows if is_junk(row[1], row[2])]

if junk_ids:
    placeholders = ",".join("?" * len(junk_ids))
    conn.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", junk_ids)
    conn.commit()
    print(f"Removed {len(junk_ids)} junk entries from {len(rows)} total.")
else:
    print(f"No junk found in {len(rows)} entries. DB is clean.")

conn.close()
