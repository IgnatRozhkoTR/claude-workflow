"""
Migrate workspace_verification_profiles to project_verification_profiles.

If the old table exists and the new one does not, create the new table,
copy data, and drop the old table.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    if "workspace_verification_profiles" not in tables:
        return
    if "project_verification_profiles" in tables:
        return

    cursor.execute("""
        CREATE TABLE project_verification_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            profile_id INTEGER NOT NULL REFERENCES verification_profiles(id) ON DELETE CASCADE,
            subpath TEXT NOT NULL DEFAULT '.',
            UNIQUE(project_id, profile_id, subpath)
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO project_verification_profiles (project_id, profile_id, subpath)
        SELECT w.project_id, wvp.profile_id, wvp.subpath
        FROM workspace_verification_profiles wvp
        JOIN workspaces w ON wvp.workspace_id = w.id
    """)

    cursor.execute("DROP TABLE workspace_verification_profiles")


step(apply_step)
