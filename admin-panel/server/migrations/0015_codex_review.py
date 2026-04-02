"""Add workspace-scoped Codex review settings and runtime status."""
from yoyo import step


_NEW_COLUMNS = [
    ("codex_review_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("codex_review_status", "TEXT NOT NULL DEFAULT 'idle'"),
    ("codex_review_started_at", "TEXT"),
    ("codex_review_completed_at", "TEXT"),
    ("codex_review_last_error", "TEXT"),
]


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(workspaces)")
    existing = {row[1] for row in cursor.fetchall()}

    for column_name, column_def in _NEW_COLUMNS:
        if column_name not in existing:
            cursor.execute(
                f"ALTER TABLE workspaces ADD COLUMN {column_name} {column_def}"
            )


step(apply_step)
