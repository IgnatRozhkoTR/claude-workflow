"""Add device-scoped global feature flags."""
from yoyo import step

step("""
    CREATE TABLE IF NOT EXISTS global_flags (
        flag_id TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
""")
