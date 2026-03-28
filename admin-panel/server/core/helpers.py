"""Helper functions for workspace operations."""
import json
import os
import re
import subprocess
from pathlib import Path

VALID_CRITERIA_TYPES = ("unit_test", "integration_test", "bdd_scenario", "custom")
DEFAULT_SOURCE_BRANCH = "develop"


def compute_phase_sequence(plan):
    """Derive phase sequence from plan execution data.

    Fixed phases: 0, 1.0-1.4, 2.0-2.1 (before plan), 4.0-4.2, 5 (after execution).
    Execution phases: 3.N.K for each plan execution item, K in 0..4.
    """
    fixed_before = ["0", "1.0", "1.1", "1.2", "1.3", "1.4", "2.0", "2.1"]
    fixed_after = ["4.0", "4.1", "4.2", "5"]

    execution = plan.get("execution", []) if isinstance(plan, dict) else []
    if not execution:
        return fixed_before + fixed_after

    exec_phases = []
    for item in execution:
        item_id = item.get("id", "")
        n = item_id.split(".")[-1] if "." in item_id else item_id
        for k in range(5):
            exec_phases.append(f"3.{n}.{k}")

    return fixed_before + exec_phases + fixed_after


def match_scope_pattern(filepath, pattern):
    """Match a file path against a scope pattern supporting ** globs."""
    pattern = pattern.rstrip("/")
    parts = re.escape(pattern).replace(r"\*\*", "DOUBLESTAR").replace(r"\*", "[^/]*").replace("DOUBLESTAR", ".*")
    regex = "^" + parts + "(/.*)?$"
    return bool(re.match(regex, filepath))


def sanitize_branch(branch):
    return re.sub(r'[^a-zA-Z0-9._-]', '-', branch)


def workspace_dir(project_path, branch):
    return Path(project_path) / ".claude" / "workspaces" / sanitize_branch(branch)


def read_json(path, default=None):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return default if default is not None else {}


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def run_git(cwd, *args):
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30
    )
    return result.returncode == 0, result.stdout, result.stderr


def find_workspace(db, project_id, branch):
    sanitized = sanitize_branch(branch)
    return db.execute(
        "SELECT * FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
        (project_id, sanitized)
    ).fetchone()
