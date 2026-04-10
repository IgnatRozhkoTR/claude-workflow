"""Shared fixtures for admin panel integration tests."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

from testing_utils import _git, GIT_ENV

# Add server/ to path for imports
SERVER_DIR = str(Path(__file__).resolve().parent.parent)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


@pytest.fixture(scope="session", autouse=True)
def setup_db(tmp_path_factory):
    """Patch DB_PATH to temp file before any app imports."""
    db_dir = tmp_path_factory.mktemp("db")
    db_file = db_dir / "admin-panel.db"

    from core import db as db_module
    db_module.DB_PATH = db_file
    db_module.init_db()
    db = db_module.get_db()
    db.execute("PRAGMA journal_mode=WAL")
    db.close()

    yield db_file


@pytest.fixture(autouse=True)
def clean_db(setup_db):
    """Truncate all tables between tests for isolation."""
    yield  # let the test run first
    # Clean up AFTER the test
    from core.db import get_db
    import sqlite3
    tables = [
        "acceptance_criteria", "review_issues", "discussions",
        "research_entries", "progress_entries", "session_history",
        "phase_history", "workspaces", "projects", "modules_enabled", "global_flags",
        "improvements",
        "verification_step_results", "verification_runs",
        "project_verification_profiles",
    ]

    def _do_clean(db):
        db.execute("PRAGMA busy_timeout = 5000")
        for table in tables:
            db.execute(f"DELETE FROM {table}")
        # Remove only user-created profiles so seeded system profiles persist
        db.execute("DELETE FROM verification_steps WHERE profile_id IN "
                   "(SELECT id FROM verification_profiles WHERE origin = 'user')")
        db.execute("DELETE FROM verification_profiles WHERE origin = 'user'")
        db.commit()
        db.close()

    try:
        _do_clean(get_db())
    except sqlite3.OperationalError:
        # If DB is locked, force close all connections and retry
        import gc
        gc.collect()
        _do_clean(get_db())


@pytest.fixture(scope="session")
def app(setup_db):
    """Create Flask test app."""
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="session")
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def git_repo(tmp_path):
    """Create a temp git repo with develop branch and initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "checkout", "-b", "develop")
    (repo / ".gitignore").write_text("")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    return str(repo)


@pytest.fixture
def git_repo_with_files(git_repo):
    """Git repo with committed source and test files."""
    repo = Path(git_repo)
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text(
        "def main():\n    print('hello')\n\ndef helper():\n    return True\n"
    )
    (repo / "src" / "utils.py").write_text(
        "def format_name(name):\n    return name.strip().title()\n"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_main.py").write_text(
        "def test_main():\n    assert True\n\ndef test_helper():\n    assert True\n"
    )
    (repo / "features").mkdir()
    (repo / "features" / "login.feature").write_text(
        "Feature: Login\n\n  Scenario: Valid login\n    Given a user\n\n  Scenario: Invalid login\n    Given no user\n"
    )
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-m", "Add source files")
    return git_repo


@pytest.fixture
def project(clean_db, git_repo):
    """Register a test project directly in DB."""
    from core.db import get_db
    db = get_db()
    project_id = "test-project"
    registered = datetime.now().isoformat()
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES (?, ?, ?, ?)",
        (project_id, "Test Project", git_repo, registered)
    )
    db.commit()
    db.close()
    return {"id": project_id, "name": "Test Project", "path": git_repo, "registered": registered}


@pytest.fixture
def workspace(project, git_repo):
    """Create a workspace at phase 0."""
    from core.db import get_db
    db = get_db()
    now = datetime.now().isoformat()
    cursor = db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, "
        "created, status, phase, scope_json, plan_json, source_branch) "
        "VALUES (?, ?, ?, ?, ?, 'active', '0', ?, ?, ?)",
        (project["id"], "feature/test", "feature-test", git_repo,
         now, '{"must":[],"may":[]}',
         '{"description":"","systemDiagram":"","execution":[]}', "develop")
    )
    ws_id = cursor.lastrowid
    db.commit()
    db.close()
    return {
        "id": ws_id,
        "project_id": project["id"],
        "branch": "feature/test",
        "sanitized_branch": "feature-test",
        "working_dir": git_repo,
        "phase": "0",
    }


@pytest.fixture
def second_workspace(project, git_repo):
    """Create a second workspace in the same project, simulating a different branch."""
    from core.db import get_db
    db = get_db()
    now = datetime.now().isoformat()
    cursor = db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, "
        "created, status, phase, scope_json, plan_json, source_branch) "
        "VALUES (?, ?, ?, ?, ?, 'active', '0', ?, ?, ?)",
        (project["id"], "feature/other", "feature-other", git_repo,
         now, '{"must":[],"may":[]}',
         '{"description":"","systemDiagram":"","execution":[]}', "develop")
    )
    ws_id = cursor.lastrowid
    db.commit()
    db.close()
    return {
        "id": ws_id,
        "project_id": project["id"],
        "branch": "feature/other",
        "sanitized_branch": "feature-other",
        "working_dir": git_repo,
        "phase": "0",
    }
