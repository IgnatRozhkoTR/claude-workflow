"""Verification profile management and execution service."""
import subprocess
import time
from datetime import datetime
from pathlib import Path


def _load_profile_with_steps(db, profile):
    """Return profile as dict with its steps appended."""
    result = dict(profile)
    result["steps"] = [dict(r) for r in db.execute(
        "SELECT * FROM verification_steps WHERE profile_id = ? ORDER BY sort_order",
        (result["id"],)
    ).fetchall()]
    return result


def _load_run_with_steps(db, run):
    """Return verification run as dict with its step results appended."""
    result = dict(run)
    result["steps"] = [dict(r) for r in db.execute(
        "SELECT * FROM verification_step_results WHERE run_id = ?", (run["id"],)
    ).fetchall()]
    return result


def get_all_profiles(db):
    """Get all verification profiles with their steps."""
    profiles = [dict(r) for r in db.execute(
        "SELECT * FROM verification_profiles ORDER BY origin, name"
    ).fetchall()]
    return [_load_profile_with_steps(db, p) for p in profiles]


def get_profile(db, profile_id):
    """Get a single profile with steps."""
    row = db.execute("SELECT * FROM verification_profiles WHERE id = ?", (profile_id,)).fetchone()
    if not row:
        return None
    return _load_profile_with_steps(db, row)


def create_profile(db, name, language, description=None, lsp_command=None, lsp_args=None,
                   lsp_install_check_command=None, lsp_install_command=None,
                   lsp_workspace_config=None, lsp_port=None):
    """Create a new user verification profile."""
    now = datetime.now().isoformat()
    cursor = db.execute(
        "INSERT INTO verification_profiles (name, language, description, origin, created_at, "
        "lsp_command, lsp_args, lsp_install_check_command, lsp_install_command, lsp_workspace_config, lsp_port) "
        "VALUES (?, ?, ?, 'user', ?, ?, ?, ?, ?, ?, ?)",
        (name.strip(), language.strip(), description.strip() if description else None, now,
         lsp_command.strip() if lsp_command else None,
         lsp_args.strip() if lsp_args else None,
         lsp_install_check_command.strip() if lsp_install_check_command else None,
         lsp_install_command.strip() if lsp_install_command else None,
         lsp_workspace_config.strip() if lsp_workspace_config else None,
         lsp_port)
    )
    return {"ok": True, "id": cursor.lastrowid}


def delete_profile(db, profile_id):
    """Delete a verification profile. Cascade deletes handle steps, assignments, and LSP instances."""
    row = db.execute("SELECT id, name FROM verification_profiles WHERE id = ?", (profile_id,)).fetchone()
    if not row:
        return None
    db.execute("DELETE FROM verification_profiles WHERE id = ?", (profile_id,))
    return dict(row)


def add_step(db, profile_id, name, command, description=None, install_check_command=None,
             install_command=None, enabled=True, sort_order=0, timeout=120, fail_severity="blocking"):
    """Add a verification step to a profile."""
    profile = db.execute("SELECT id FROM verification_profiles WHERE id = ?", (profile_id,)).fetchone()
    if not profile:
        return {"error": "profile_not_found"}
    now = datetime.now().isoformat()
    cursor = db.execute(
        "INSERT INTO verification_steps (profile_id, name, description, command, install_check_command, "
        "install_command, enabled, sort_order, timeout, fail_severity, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (profile_id, name.strip(), description.strip() if description else None, command.strip(),
         install_check_command.strip() if install_check_command else None,
         install_command.strip() if install_command else None,
         1 if enabled else 0, sort_order, timeout, fail_severity, now)
    )
    return {"ok": True, "id": cursor.lastrowid}


def update_step(db, step_id, **kwargs):
    """Update a verification step's fields."""
    row = db.execute("SELECT * FROM verification_steps WHERE id = ?", (step_id,)).fetchone()
    if not row:
        return {"error": "step_not_found"}

    allowed = {"name", "description", "command", "install_check_command", "install_command",
               "enabled", "sort_order", "timeout", "fail_severity"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"error": "nothing_to_update"}

    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [step_id]
    db.execute(f"UPDATE verification_steps SET {set_clause} WHERE id = ?", values)
    return {"ok": True}


def delete_step(db, step_id):
    """Delete a verification step."""
    row = db.execute("SELECT id FROM verification_steps WHERE id = ?", (step_id,)).fetchone()
    if not row:
        return {"error": "step_not_found"}
    db.execute("DELETE FROM verification_steps WHERE id = ?", (step_id,))
    return {"ok": True}


def get_project_profiles(db, project_id):
    """Get profiles assigned to a project."""
    rows = db.execute(
        "SELECT pp.id as assignment_id, pp.subpath, vp.* FROM project_verification_profiles pp "
        "JOIN verification_profiles vp ON pp.profile_id = vp.id "
        "WHERE pp.project_id = ? ORDER BY vp.name",
        (project_id,)
    ).fetchall()
    result = []
    for r in rows:
        result.append(_load_profile_with_steps(db, r))
    return result


def assign_profile(db, project_id, profile_id, subpath="."):
    """Assign a profile to a project."""
    profile = db.execute("SELECT id FROM verification_profiles WHERE id = ?", (profile_id,)).fetchone()
    if not profile:
        return {"error": "profile_not_found"}
    existing = db.execute(
        "SELECT id FROM project_verification_profiles WHERE project_id = ? AND profile_id = ? AND subpath = ?",
        (project_id, profile_id, subpath)
    ).fetchone()
    if existing:
        return {"error": "already_assigned"}
    cursor = db.execute(
        "INSERT INTO project_verification_profiles (project_id, profile_id, subpath) VALUES (?, ?, ?)",
        (project_id, profile_id, subpath)
    )
    return {"ok": True, "id": cursor.lastrowid}


def unassign_profile(db, assignment_id, project_id):
    """Remove a profile assignment from a project."""
    row = db.execute(
        "SELECT id FROM project_verification_profiles WHERE id = ? AND project_id = ?",
        (assignment_id, project_id)
    ).fetchone()
    if not row:
        return {"error": "assignment_not_found"}
    db.execute("DELETE FROM project_verification_profiles WHERE id = ?", (assignment_id,))
    return {"ok": True}


def _get_project_id_for_workspace(db, workspace_id):
    """Look up the project_id for a given workspace."""
    row = db.execute("SELECT project_id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    return row["project_id"] if row else None


def run_verification(db, workspace_id, phase, working_dir):
    """Run all assigned verification profiles for a workspace. Returns (passed, run_id)."""
    project_id = _get_project_id_for_workspace(db, workspace_id)
    assignments = db.execute(
        "SELECT pp.subpath, vp.id as profile_id, vp.name as profile_name "
        "FROM project_verification_profiles pp "
        "JOIN verification_profiles vp ON pp.profile_id = vp.id "
        "WHERE pp.project_id = ?",
        (project_id,)
    ).fetchall() if project_id else []

    if not assignments:
        return True, None

    now = datetime.now().isoformat()
    run_cursor = db.execute(
        "INSERT INTO verification_runs (workspace_id, phase, status, started_at) VALUES (?, ?, 'running', ?)",
        (workspace_id, phase, now)
    )
    run_id = run_cursor.lastrowid
    all_passed = True

    for assignment in assignments:
        profile_id = assignment["profile_id"]
        profile_name = assignment["profile_name"]
        subpath = assignment["subpath"]
        step_dir = str(Path(working_dir) / subpath) if subpath != "." else working_dir

        steps = db.execute(
            "SELECT * FROM verification_steps WHERE profile_id = ? AND enabled = 1 ORDER BY sort_order",
            (profile_id,)
        ).fetchall()

        for step in steps:
            start_time = time.time()
            status = "passed"
            output = ""

            if step["install_check_command"]:
                check_result = subprocess.run(
                    step["install_check_command"], shell=True, cwd=step_dir,
                    capture_output=True, text=True, timeout=10
                )
                if check_result.returncode != 0:
                    if step["install_command"]:
                        install_result = subprocess.run(
                            step["install_command"], shell=True, cwd=step_dir,
                            capture_output=True, text=True, timeout=300
                        )
                        if install_result.returncode != 0:
                            status = "skipped"
                            output = f"Install failed: {install_result.stderr.strip()}"
                            duration_ms = int((time.time() - start_time) * 1000)
                            db.execute(
                                "INSERT INTO verification_step_results (run_id, step_name, profile_name, status, output, duration_ms) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (run_id, step["name"], profile_name, status, output, duration_ms)
                            )
                            continue
                        output = "Tool installed. "
                    else:
                        status = "skipped"
                        output = f"Tool not found (check: {step['install_check_command']}), no install command configured."
                        duration_ms = int((time.time() - start_time) * 1000)
                        db.execute(
                            "INSERT INTO verification_step_results (run_id, step_name, profile_name, status, output, duration_ms) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (run_id, step["name"], profile_name, status, output, duration_ms)
                        )
                        continue

            timeout_val = step["timeout"] if step["timeout"] > 0 else None
            try:
                result = subprocess.run(
                    step["command"], shell=True, cwd=step_dir,
                    capture_output=True, text=True, timeout=timeout_val
                )
                if result.returncode != 0:
                    status = "warning" if step["fail_severity"] == "warning" else "failed"
                    output += result.stdout.strip() + "\n" + result.stderr.strip()
                    if step["fail_severity"] == "blocking":
                        all_passed = False
                else:
                    output += result.stdout.strip()
            except subprocess.TimeoutExpired:
                status = "failed" if step["fail_severity"] == "blocking" else "warning"
                output += f"Timed out after {step['timeout']}s"
                if step["fail_severity"] == "blocking":
                    all_passed = False
            except Exception as e:
                status = "failed" if step["fail_severity"] == "blocking" else "warning"
                output += f"Error: {str(e)}"
                if step["fail_severity"] == "blocking":
                    all_passed = False

            duration_ms = int((time.time() - start_time) * 1000)
            db.execute(
                "INSERT INTO verification_step_results (run_id, step_name, profile_name, status, output, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, step["name"], profile_name, status, output.strip(), duration_ms)
            )

    final_status = "passed" if all_passed else "failed"
    db.execute(
        "UPDATE verification_runs SET status = ?, completed_at = ? WHERE id = ?",
        (final_status, datetime.now().isoformat(), run_id)
    )
    return all_passed, run_id


def get_verification_results(db, workspace_id, phase=None, run_id=None):
    """Get verification run results."""
    if run_id:
        run = db.execute(
            "SELECT * FROM verification_runs WHERE id = ? AND workspace_id = ?",
            (run_id, workspace_id)
        ).fetchone()
        if not run:
            return None
        return _load_run_with_steps(db, run)

    query = "SELECT * FROM verification_runs WHERE workspace_id = ?"
    params = [workspace_id]
    if phase:
        query += " AND phase = ?"
        params.append(phase)
    query += " ORDER BY started_at DESC LIMIT 1"

    run = db.execute(query, params).fetchone()
    if not run:
        return None
    return _load_run_with_steps(db, run)
