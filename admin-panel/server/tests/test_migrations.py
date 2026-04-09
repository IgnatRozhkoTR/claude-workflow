"""Tests for migration 0017_repoint_format_tools."""
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

SERVER_DIR = str(Path(__file__).resolve().parent.parent)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_LEGACY_JAR = "~/.claude/tools/google-java-format.jar"
_LEGACY_INSTALL = "mkdir -p ~/.claude/tools && curl -sL -o ~/.claude/tools/google-java-format.jar"
_NEW_JAR = "${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar"
_NEW_INSTALL = "mkdir -p ${GOVERNED_WORKFLOW_TOOLS_DIR} && curl -sL -o ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar"

_LEGACY_COMMAND = (
    "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.java'; "
    "git ls-files --others --exclude-standard -- '*.java'; } | sort -u | "
    f"xargs -r java -jar {_LEGACY_JAR} --replace"
)
_LEGACY_CHECK = f"test -f {_LEGACY_JAR}"
_LEGACY_INSTALL_CMD = (
    f"{_LEGACY_INSTALL} "
    "https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar"
)


@pytest.fixture
def seeded_db(tmp_path):
    """SQLite DB with the minimal schema and a legacy-path Format step."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE verification_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            language TEXT NOT NULL,
            description TEXT,
            origin TEXT NOT NULL DEFAULT 'system'
        )
    """)
    cursor.execute("""
        CREATE TABLE verification_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES verification_profiles(id),
            name TEXT NOT NULL,
            description TEXT,
            command TEXT,
            install_check_command TEXT,
            install_command TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            timeout INTEGER NOT NULL DEFAULT 120,
            fail_severity TEXT NOT NULL DEFAULT 'blocking',
            created_at TEXT
        )
    """)

    cursor.execute(
        "INSERT INTO verification_profiles (name, language, origin) VALUES (?, ?, ?)",
        ("Java (Gradle)", "java", "system"),
    )
    profile_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO verification_steps "
        "(profile_id, name, description, command, install_check_command, install_command) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            profile_id,
            "Format",
            "Auto-format Java code with google-java-format",
            _LEGACY_COMMAND,
            _LEGACY_CHECK,
            _LEGACY_INSTALL_CMD,
        ),
    )

    # A row that must NOT be modified (different tool, no legacy substring)
    cursor.execute(
        "INSERT INTO verification_steps "
        "(profile_id, name, description, command, install_check_command, install_command) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            profile_id,
            "Compilation",
            "Compile Java sources",
            "./gradlew compileJava -q",
            "test -f ./gradlew",
            None,
        ),
    )

    conn.commit()
    return conn


def _load_migration():
    """Import the migration module and return its apply_step function.

    yoyo.step is called at module level in migrations. We temporarily replace
    it with a no-op that just records the function so we can call apply_step
    directly in tests without needing a full yoyo backend context.
    """
    import yoyo as _yoyo

    original_step = _yoyo.step
    captured = {}

    def _stub_step(fn, *args, **kwargs):
        captured["apply_step"] = fn

    _yoyo.step = _stub_step
    try:
        module_name = "migration_0017_repoint_format_tools"
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(
            module_name,
            str(MIGRATIONS_DIR / "0017_repoint_format_tools.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
    finally:
        _yoyo.step = original_step

    return captured["apply_step"]


def test_legacy_row_is_repointed(seeded_db):
    """Running 0017 on a DB with a legacy ~/.claude/tools row rewrites it."""
    apply_step = _load_migration()
    apply_step(seeded_db)
    seeded_db.commit()

    cursor = seeded_db.cursor()
    cursor.execute("SELECT command, install_check_command, install_command FROM verification_steps WHERE name = 'Format'")
    row = cursor.fetchone()

    assert _LEGACY_JAR not in row["command"]
    assert _NEW_JAR in row["command"]

    assert _LEGACY_JAR not in row["install_check_command"]
    assert _NEW_JAR in row["install_check_command"]

    assert "~/.claude/tools" not in row["install_command"]
    assert "${GOVERNED_WORKFLOW_TOOLS_DIR}" in row["install_command"]


def test_migration_is_idempotent(seeded_db):
    """Running 0017 twice does not alter rows after the first application."""
    apply_step = _load_migration()

    apply_step(seeded_db)
    seeded_db.commit()

    cursor = seeded_db.cursor()
    cursor.execute("SELECT command, install_check_command, install_command FROM verification_steps WHERE name = 'Format'")
    after_first = dict(cursor.fetchone())

    apply_step(seeded_db)
    seeded_db.commit()

    cursor.execute("SELECT command, install_check_command, install_command FROM verification_steps WHERE name = 'Format'")
    after_second = dict(cursor.fetchone())

    assert after_first == after_second


def test_unrelated_row_is_unchanged(seeded_db):
    """A step that doesn't reference the legacy jar is left untouched."""
    apply_step = _load_migration()
    apply_step(seeded_db)
    seeded_db.commit()

    cursor = seeded_db.cursor()
    cursor.execute("SELECT command FROM verification_steps WHERE name = 'Compilation'")
    row = cursor.fetchone()

    assert row["command"] == "./gradlew compileJava -q"


def test_fresh_db_with_env_var_form_is_noop(tmp_path):
    """A fresh DB that already has env-var form rows is left unchanged."""
    db_path = tmp_path / "fresh.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE verification_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            language TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'system'
        )
    """)
    cursor.execute("""
        CREATE TABLE verification_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            command TEXT,
            install_check_command TEXT,
            install_command TEXT
        )
    """)

    correct_command = (
        "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.java'; "
        "git ls-files --others --exclude-standard -- '*.java'; } | sort -u | "
        f"xargs -r java -jar {_NEW_JAR} --replace"
    )
    cursor.execute(
        "INSERT INTO verification_profiles (name, language) VALUES (?, ?)",
        ("Java (Gradle)", "java"),
    )
    pid = cursor.lastrowid
    cursor.execute(
        "INSERT INTO verification_steps (profile_id, name, command, install_check_command, install_command) VALUES (?, ?, ?, ?, ?)",
        (pid, "Format", correct_command, f"test -f {_NEW_JAR}", _NEW_INSTALL + " https://example.com/gjf.jar"),
    )
    conn.commit()

    apply_step = _load_migration()
    apply_step(conn)
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("SELECT command FROM verification_steps WHERE name = 'Format'")
    row = cursor.fetchone()
    assert row["command"] == correct_command
