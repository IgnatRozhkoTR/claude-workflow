"""Helper functions shared across test modules."""
import json
import os
import subprocess
from datetime import datetime

# Git environment to avoid needing global git config
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
}


def _git(cwd, *args):
    """Run a git command in the given directory."""
    subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=GIT_ENV,
    )


def set_phase(ws_id, phase, **kwargs):
    """Set workspace phase (and optionally other columns) in DB."""
    from db import get_db
    db = get_db()
    updates = ["phase = ?"]
    params = [phase]
    for key, value in kwargs.items():
        updates.append(f"{key} = ?")
        params.append(value)
    params.append(ws_id)
    db.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    db.close()


def add_progress(ws_id, phase_key, summary="Done"):
    """Insert a progress entry for gate validation."""
    from db import get_db
    now = datetime.now().isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO progress_entries (workspace_id, phase, summary, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_id, phase_key, summary, now, now)
    )
    db.commit()
    db.close()


def add_research(ws_id, topic="Test topic", findings=None, proven=0, discussion_id=None):
    """Insert a research entry."""
    from db import get_db
    if findings is None:
        findings = [{"summary": "Found something", "details": "Details", "proof": {"type": "code", "file": "src/main.py", "line_start": 1, "line_end": 5}}]
    now = datetime.now().isoformat()
    db = get_db()
    cursor = db.execute(
        "INSERT INTO research_entries (workspace_id, topic, findings_json, proven, created_at, discussion_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ws_id, topic, json.dumps(findings), proven, now, discussion_id)
    )
    entry_id = cursor.lastrowid
    db.commit()
    db.close()
    return entry_id


def add_comment(workspace_id, scope="plan", target="task1", text="Review this",
                resolution=None, file_path=None, line_start=None, line_end=None, author="user"):
    """Insert a scoped comment into the discussions table."""
    from db import get_db
    db = get_db()
    cursor = db.execute(
        "INSERT INTO discussions (workspace_id, scope, target, text, author, status, resolution, "
        "file_path, line_start, line_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)",
        (workspace_id, scope, target, text, author, resolution, file_path, line_start, line_end,
         datetime.now().isoformat())
    )
    db.commit()
    comment_id = cursor.lastrowid
    db.close()
    return comment_id


def add_discussion(workspace_id, text="Architecture question", author="agent", type="general"):
    """Insert a general discussion (scope IS NULL)."""
    from db import get_db
    db = get_db()
    cursor = db.execute(
        "INSERT INTO discussions (workspace_id, text, author, status, created_at, type) "
        "VALUES (?, ?, ?, 'open', ?, ?)",
        (workspace_id, text, author, datetime.now().isoformat(), type)
    )
    db.commit()
    discussion_id = cursor.lastrowid
    db.close()
    return discussion_id


def add_review_issue(ws_id, file_path="src/main.py", code_snippet="def main():", severity="major"):
    """Insert a review issue."""
    from db import get_db
    now = datetime.now().isoformat()
    db = get_db()
    cursor = db.execute(
        "INSERT INTO review_issues (workspace_id, file_path, line_start, line_end, "
        "severity, description, code_snippet, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ws_id, file_path, 1, 3, severity, "Test issue", code_snippet, now)
    )
    issue_id = cursor.lastrowid
    db.commit()
    db.close()
    return issue_id


def add_criterion(ws_id, cr_type="unit_test", description="Test criterion",
                  status="proposed", source="user", details_json=None):
    """Insert an acceptance criterion."""
    from db import get_db
    now = datetime.now().isoformat()
    db = get_db()
    cursor = db.execute(
        "INSERT INTO acceptance_criteria (workspace_id, type, description, details_json, "
        "source, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ws_id, cr_type, description, details_json, source, status, now)
    )
    criterion_id = cursor.lastrowid
    db.commit()
    db.close()
    return criterion_id


def make_plan_json(num_phases=2):
    """Generate a valid plan JSON with the given number of execution sub-phases."""
    execution = []
    for i in range(1, num_phases + 1):
        execution.append({
            "id": f"3.{i}",
            "name": f"Sub-phase {i}",
            "tasks": [{"title": f"Task {i}", "files": [f"src/phase{i}/file.py"], "agent": "middle-backend-engineer"}]
        })
    return json.dumps({"description": "Test plan description", "systemDiagram": "graph LR", "execution": execution})
