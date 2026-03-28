"""
Add discussion_id and summary columns to research_entries.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(research_entries)")
    existing = {row[1] for row in cursor.fetchall()}

    if "discussion_id" not in existing:
        cursor.execute(
            "ALTER TABLE research_entries ADD COLUMN discussion_id INTEGER"
        )
    if "summary" not in existing:
        cursor.execute("ALTER TABLE research_entries ADD COLUMN summary TEXT")


step(apply_step)
