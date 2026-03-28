"""
Add commit_hash column to phase_history.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(phase_history)")
    existing = {row[1] for row in cursor.fetchall()}

    if "commit_hash" not in existing:
        cursor.execute("ALTER TABLE phase_history ADD COLUMN commit_hash TEXT")


step(apply_step)
