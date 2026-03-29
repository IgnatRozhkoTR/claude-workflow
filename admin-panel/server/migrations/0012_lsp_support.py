"""
Add LSP (Language Server Protocol) support:
- New columns on verification_profiles for LSP server configuration.
- New column on project_verification_profiles to enable/disable LSP per project.
- New lsp_instances table to track running LSP processes.
- Seed LSP data for existing system profiles.
"""
from yoyo import step

_VERIFICATION_PROFILES_COLUMNS = [
    ("lsp_command", "TEXT"),
    ("lsp_args", "TEXT"),
    ("lsp_install_check_command", "TEXT"),
    ("lsp_install_command", "TEXT"),
    ("lsp_workspace_config", "TEXT"),
    ("lsp_port", "INTEGER"),
]

_PROJECT_VERIFICATION_PROFILES_COLUMNS = [
    ("lsp_enabled", "INTEGER NOT NULL DEFAULT 1"),
]


def apply_step(conn):
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(verification_profiles)")
    existing_vp = {row[1] for row in cursor.fetchall()}

    for column_name, column_def in _VERIFICATION_PROFILES_COLUMNS:
        if column_name not in existing_vp:
            cursor.execute(
                f"ALTER TABLE verification_profiles ADD COLUMN {column_name} {column_def}"
            )

    cursor.execute("PRAGMA table_info(project_verification_profiles)")
    existing_pvp = {row[1] for row in cursor.fetchall()}

    for column_name, column_def in _PROJECT_VERIFICATION_PROFILES_COLUMNS:
        if column_name not in existing_pvp:
            cursor.execute(
                f"ALTER TABLE project_verification_profiles ADD COLUMN {column_name} {column_def}"
            )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lsp_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            profile_id INTEGER NOT NULL REFERENCES verification_profiles(id) ON DELETE CASCADE,
            pid INTEGER,
            port INTEGER,
            status TEXT NOT NULL DEFAULT 'stopped',
            started_at TEXT,
            error_message TEXT,
            UNIQUE(project_id, profile_id)
        )
    """)

    cursor.execute("""
        UPDATE verification_profiles SET
            lsp_command = 'jdtls',
            lsp_args = '["--jvm-arg=-Xmx1G"]',
            lsp_install_check_command = 'which jdtls',
            lsp_install_command = 'brew install jdtls'
        WHERE name = 'Java (Gradle)' AND origin = 'system'
    """)

    cursor.execute("""
        UPDATE verification_profiles SET
            lsp_command = 'jdtls',
            lsp_args = '["--jvm-arg=-Xmx1G"]',
            lsp_install_check_command = 'which jdtls',
            lsp_install_command = 'brew install jdtls'
        WHERE name = 'Java (Maven)' AND origin = 'system'
    """)

    cursor.execute("""
        UPDATE verification_profiles SET
            lsp_command = 'pyright-langserver',
            lsp_args = '["--stdio"]',
            lsp_install_check_command = 'which pyright-langserver',
            lsp_install_command = 'npm install -g pyright'
        WHERE name = 'Python' AND origin = 'system'
    """)

    cursor.execute("""
        UPDATE verification_profiles SET
            lsp_command = 'typescript-language-server',
            lsp_args = '["--stdio"]',
            lsp_install_check_command = 'which typescript-language-server',
            lsp_install_command = 'npm install -g typescript-language-server typescript'
        WHERE name = 'TypeScript' AND origin = 'system'
    """)


step(apply_step)
