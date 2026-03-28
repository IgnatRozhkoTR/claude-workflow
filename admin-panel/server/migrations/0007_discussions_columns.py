"""
Add type, hidden, and resolution columns to discussions.
Backfill resolution for review rows.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(discussions)")
    existing = {row[1] for row in cursor.fetchall()}

    if "type" not in existing:
        cursor.execute("ALTER TABLE discussions ADD COLUMN type TEXT DEFAULT 'general'")
    if "hidden" not in existing:
        cursor.execute("ALTER TABLE discussions ADD COLUMN hidden INTEGER DEFAULT 0")
    if "resolution" not in existing:
        cursor.execute("ALTER TABLE discussions ADD COLUMN resolution TEXT")

    cursor.execute(
        "UPDATE discussions SET resolution = 'open' WHERE scope = 'review' AND resolution IS NULL"
    )


step(apply_step)
