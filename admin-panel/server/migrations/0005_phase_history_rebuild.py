"""
Rebuild phase_history table if from_phase/to_phase are INTEGER columns
(legacy schema stored phase numbers as integers instead of TEXT).
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(phase_history)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    if columns.get("from_phase", "").upper() != "INTEGER":
        return

    cursor.execute("DROP TABLE phase_history")
    cursor.execute("""
        CREATE TABLE phase_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            from_phase TEXT NOT NULL,
            to_phase TEXT NOT NULL,
            time TEXT NOT NULL
        )
    """)


step(apply_step)
