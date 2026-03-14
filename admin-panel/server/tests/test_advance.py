"""Tests for advance endpoints (approve/reject) and perform_advance advancers."""
from testing_utils import set_phase, add_progress, add_research, add_discussion, add_review_issue, add_criterion, add_comment, make_plan_json


# ── Approve/Reject endpoint tests ────────────────────────────────────────────


def test_approve_at_plan_review(client, workspace):
    """Approve at phase 2.1 → advances to first execution phase."""
    plan = make_plan_json(2)
    set_phase(workspace["id"], "2.1", gate_nonce="nonce-abc", plan_json=plan, plan_status="approved")
    add_progress(workspace["id"], "2", "Planning done")

    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "nonce-abc"})
    assert r.status_code == 200
    assert r.json["phase"] == "3.1.0"


def test_approve_at_code_review(client, workspace):
    """Approve at 3.1.3 → advances to 3.1.4 (commit)."""
    plan = make_plan_json(1)
    set_phase(workspace["id"], "3.1.3", gate_nonce="nonce-xyz", plan_json=plan,
              plan_status="approved", scope_status="approved")

    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "nonce-xyz"})
    assert r.status_code == 200
    assert r.json["phase"] == "3.1.4"


def test_approve_at_final_gate(client, workspace):
    """Approve at 4.2 → phase 5."""
    plan = make_plan_json(1)
    set_phase(workspace["id"], "4.2", gate_nonce="nonce-final", plan_json=plan,
              plan_status="approved", scope_status="approved")

    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "nonce-final"})
    assert r.status_code == 200
    assert r.json["phase"] == "5"


def test_approve_wrong_nonce(client, workspace):
    set_phase(workspace["id"], "2.1", gate_nonce="correct-nonce")

    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "wrong-nonce"})
    assert r.status_code == 403


def test_approve_not_at_gate(client, workspace):
    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "any"})
    assert r.status_code == 400


def test_approve_missing_token(client, workspace):
    set_phase(workspace["id"], "2.1", gate_nonce="nonce")

    r = client.post("/api/ws/test-project/feature/test/approve", json={})
    assert r.status_code == 400


def test_reject_at_plan_review(client, workspace):
    set_phase(workspace["id"], "2.1", gate_nonce="nonce-rej")

    r = client.post("/api/ws/test-project/feature/test/reject", json={"token": "nonce-rej"})
    assert r.status_code == 200
    assert r.json["phase"] == "2.0"


def test_reject_at_code_review(client, workspace):
    set_phase(workspace["id"], "3.1.3", gate_nonce="nonce-cr")

    r = client.post("/api/ws/test-project/feature/test/reject", json={"token": "nonce-cr"})
    assert r.status_code == 200
    assert r.json["phase"] == "3.1.2"


def test_reject_at_final_gate(client, workspace):
    set_phase(workspace["id"], "4.2", gate_nonce="nonce-f")

    r = client.post("/api/ws/test-project/feature/test/reject", json={"token": "nonce-f"})
    assert r.status_code == 200
    assert r.json["phase"] == "4.1"


def test_reject_with_comments(client, workspace):
    set_phase(workspace["id"], "2.1", gate_nonce="nonce-c")

    r = client.post(
        "/api/ws/test-project/feature/test/reject",
        json={"token": "nonce-c", "comments": "Fix the plan"},
    )
    assert r.status_code == 200

    from db import get_db
    db = get_db()
    comment = db.execute(
        "SELECT * FROM discussions WHERE workspace_id = ? AND scope = 'phase'", (workspace["id"],)
    ).fetchone()
    db.close()
    assert comment["text"] == "Fix the plan"
    assert comment["scope"] == "phase"


# ── Advancer tests (perform_advance directly) ─────────────────────────────────


from advance_service import perform_advance
from db import get_db


def _get_ws_row(ws_id):
    """Fetch a fresh workspace row from DB."""
    db = get_db()
    row = db.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    db.close()
    return row


def test_init_advancer(workspace, project):
    """Phase 0 → 1.0 always succeeds."""
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "1.0"


def test_assessment_blocked_without_progress(workspace, project):
    set_phase(workspace["id"], "1.0")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422


def test_assessment_passes_with_progress(workspace, project):
    set_phase(workspace["id"], "1.0")
    add_progress(workspace["id"], "1.0", "Assessment done")
    add_discussion(workspace["id"], type="research")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "1.1"


def test_research_blocked_no_entries(workspace, project):
    set_phase(workspace["id"], "1.1")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422


def test_research_passes(workspace, project):
    set_phase(workspace["id"], "1.1")
    disc_id = add_discussion(workspace["id"], type="research")
    add_research(workspace["id"], discussion_id=disc_id)
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={"no_further_research_needed": True})
    assert code == 200
    assert result["phase"] == "1.2"


def test_prover_blocked_unproven(workspace, project):
    set_phase(workspace["id"], "1.2")
    add_research(workspace["id"], proven=0)
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422


def test_prover_blocked_rejected(workspace, project):
    set_phase(workspace["id"], "1.2")
    add_research(workspace["id"], proven=-1)
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422


def test_prover_passes(workspace, project):
    set_phase(workspace["id"], "1.2")
    add_research(workspace["id"], proven=1)
    add_progress(workspace["id"], "1", "Research done")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "1.3"


def test_impact_analysis_passes(workspace, project):
    set_phase(workspace["id"], "1.3")
    add_progress(workspace["id"], "1.3", "Impact analyzed")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "2.0"


def test_plan_blocked_no_plan(workspace, project):
    set_phase(workspace["id"], "2.0")
    add_progress(workspace["id"], "2", "Planning done")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422


def test_plan_passes(workspace, project):
    plan = make_plan_json(2)
    set_phase(workspace["id"], "2.0", plan_json=plan, plan_status="approved")
    add_progress(workspace["id"], "2", "Planning done")
    add_criterion(workspace["id"], status="accepted")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 202
    assert result["phase"] == "2.1"


def test_plan_blocked_by_pending_criteria(client, workspace):
    plan = make_plan_json(1)
    set_phase(workspace["id"], "2.1", gate_nonce="nonce-criteria", plan_json=plan, plan_status="approved")
    add_criterion(workspace["id"], status="proposed")

    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "nonce-criteria"})
    assert r.status_code == 400
    assert "acceptance criteria" in r.json["error"]


def test_user_gate_blocks_advance(workspace, project):
    set_phase(workspace["id"], "2.1")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 409


# ── AgenticReviewAdvancer (phase 4.0) ──────────────────────────────────────────

import json
from pathlib import Path
from testing_utils import _git, GIT_ENV


def _setup_execution_phase(ws_id, phase, num_plan_phases=3):
    """Set up workspace for an execution phase with all required fields."""
    plan = make_plan_json(num_plan_phases)
    scope = {f"3.{n}": {"must": ["src/"], "may": ["tests/"]} for n in range(1, num_plan_phases + 1)}
    set_phase(
        ws_id, phase,
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
        scope_json=json.dumps(scope),
    )


def test_agentic_review_blocked_without_progress(workspace, project):
    """Phase 4.0 blocks without a progress entry."""
    plan = make_plan_json(1)
    set_phase(
        workspace["id"], "4.0",
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
    )

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422
    assert result["status"] == "blocked"


def test_agentic_review_passes_with_progress(workspace, project):
    """Phase 4.0 advances to 4.1 when progress entry exists."""
    plan = make_plan_json(1)
    set_phase(
        workspace["id"], "4.0",
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
    )
    add_progress(workspace["id"], "4.0", "Agentic review completed")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "4.1"


# ── AddressFixAdvancer (phase 4.1) ─────────────────────────────────────────────


def _add_review_issue_row(ws_id, file_path="src/main.py", code_snippet="def main():",
                          resolution="open", validated=0):
    """Insert a review issue with full control over resolution and validated fields."""
    from datetime import datetime
    now = datetime.now().isoformat()
    db = get_db()
    cursor = db.execute(
        "INSERT INTO review_issues (workspace_id, file_path, line_start, line_end, "
        "severity, description, code_snippet, resolution, validated, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ws_id, file_path, 1, 5, "major", "Test issue", code_snippet, resolution, validated, now)
    )
    issue_id = cursor.lastrowid
    db.commit()
    db.close()
    return issue_id


def test_address_fix_blocked_without_progress(workspace, project):
    """Phase 4.1 blocks without a progress entry for '4'."""
    plan = make_plan_json(1)
    set_phase(
        workspace["id"], "4.1",
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
    )

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422
    assert result["status"] == "blocked"


def test_address_fix_passes_no_issues(workspace, project):
    """Phase 4.1 advances to 4.2 when progress exists and no review issues."""
    plan = make_plan_json(1)
    set_phase(
        workspace["id"], "4.1",
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
    )
    add_progress(workspace["id"], "4", "All fixes addressed")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 202
    assert result["phase"] == "4.2"


def test_address_fix_blocked_unresolved_review_comment(workspace, project):
    """Phase 4.1 blocks when a scope='review' discussion is still open (ReviewGuard)."""
    plan = make_plan_json(1)
    set_phase(
        workspace["id"], "4.1",
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
    )
    add_progress(workspace["id"], "4", "Addressing fixes")
    add_comment(workspace["id"], scope="review", text="Unresolved review finding")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422
    assert "guard_errors" in result
    assert any(e["guard"] == "review_resolved" for e in result["guard_errors"])


def test_address_fix_passes_all_fixed_validated(workspace, project):
    """Phase 4.1 advances when all issues are fixed, validated, and code changed."""
    plan = make_plan_json(1)
    set_phase(
        workspace["id"], "4.1",
        plan_json=plan,
        plan_status="approved",
        scope_status="approved",
    )
    add_progress(workspace["id"], "4", "All fixes addressed")
    # code_snippet is "old buggy code" which does NOT exist in any file
    _add_review_issue_row(
        workspace["id"],
        file_path="src/main.py",
        code_snippet="old buggy code that was removed",
        resolution="fixed",
        validated=1,
    )

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 202
    assert result["phase"] == "4.2"


# ── ExecutionAdvancer (phase 3.N.K) ────────────────────────────────────────────


def test_execution_implementation_blocked_no_changes(workspace, project):
    """Phase 3.1.0 blocks when no git changes match must-scope."""
    _setup_execution_phase(workspace["id"], "3.1.0")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422
    assert "must-scope" in result["message"]


def test_execution_implementation_passes_with_changes(workspace, project):
    """Phase 3.1.0 advances to 3.1.1 when files matching must-scope are committed."""
    _setup_execution_phase(workspace["id"], "3.1.0")

    working_dir = workspace["working_dir"]
    _git(working_dir, "checkout", "-b", "feature/test")
    src_dir = Path(working_dir) / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "feature.py").write_text("def feature():\n    return True\n")
    _git(working_dir, "add", ".")
    _git(working_dir, "commit", "-m", "Add feature implementation")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "3.1.1"


def test_execution_validation_routes_to_review(workspace, project):
    """Phase 3.1.1 routes to 3.1.3 (code review gate) when validation is clean."""
    _setup_execution_phase(workspace["id"], "3.1.1")

    ws_dir = Path(project["path"]) / ".claude" / "workspaces" / "feature-test"
    validation_dir = ws_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "3.1.json").write_text(json.dumps({"status": "clean"}))

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 202
    assert result["phase"] == "3.1.3"


def test_execution_validation_routes_to_fixes(workspace, project):
    """Phase 3.1.1 routes to 3.1.2 (fixes) when validation is dirty."""
    _setup_execution_phase(workspace["id"], "3.1.1")

    ws_dir = Path(project["path"]) / ".claude" / "workspaces" / "feature-test"
    validation_dir = ws_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "3.1.json").write_text(json.dumps({"status": "dirty"}))

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "3.1.2"


def test_execution_commit_blocked_no_hash(workspace, project):
    """Phase 3.1.4 blocks when no commit_hash is provided."""
    _setup_execution_phase(workspace["id"], "3.1.4")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={})
    assert code == 422
    assert "commit_hash" in result["message"]


def test_execution_commit_blocked_invalid_hash(workspace, project):
    """Phase 3.1.4 blocks when an invalid commit_hash is provided."""
    _setup_execution_phase(workspace["id"], "3.1.4")

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={"commit_hash": "deadbeef123"})
    assert code == 422
    assert "not found" in result["message"]


def test_execution_commit_passes(workspace, project):
    """Phase 3.1.4 advances when a valid commit hash and progress are provided."""
    _setup_execution_phase(workspace["id"], "3.1.4")
    add_progress(workspace["id"], "3.1", "Sub-phase 1 complete")

    working_dir = workspace["working_dir"]
    src_dir = Path(working_dir) / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "committed.py").write_text("print('committed')\n")
    _git(working_dir, "add", ".")
    _git(working_dir, "commit", "-m", "Commit for sub-phase")

    import subprocess
    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=working_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={"commit_hash": commit_hash})
    assert code == 200
    assert result["phase"] == "3.2.0"


# ── ExecutionAdvancer validate_all integration (acceptance criteria) ─────────


def _make_commit(working_dir):
    """Create a dummy commit and return its hash."""
    import subprocess
    src_dir = Path(working_dir) / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "committed.py").write_text(f"print('commit {datetime.now().isoformat()}')\n")
    _git(working_dir, "add", ".")
    _git(working_dir, "commit", "-m", "Test commit")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=working_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()


from datetime import datetime


def test_last_commit_blocked_by_failing_criteria(workspace, project):
    """Last sub-phase commit is blocked when an accepted criterion fails validation."""
    _setup_execution_phase(workspace["id"], "3.1.4", num_plan_phases=1)
    add_progress(workspace["id"], "3.1", "Sub-phase 1 complete")

    add_criterion(
        workspace["id"],
        cr_type="unit_test",
        status="accepted",
        details_json=json.dumps({"file": "tests/nonexistent_test.py", "test_names": ["test_foo"]}),
    )

    commit_hash = _make_commit(workspace["working_dir"])

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={"commit_hash": commit_hash})
    assert code == 422
    assert "acceptance criteria" in result["message"].lower()


def test_last_commit_passes_with_valid_criteria(workspace, project):
    """Last sub-phase commit passes when all accepted criteria are valid (custom + pre-validated)."""
    _setup_execution_phase(workspace["id"], "3.1.4", num_plan_phases=1)
    add_progress(workspace["id"], "3.1", "Sub-phase 1 complete")

    add_criterion(
        workspace["id"],
        cr_type="custom",
        status="accepted",
        details_json=None,
    )
    # Mark the custom criterion as validated (user approved via admin panel)
    db = get_db()
    db.execute(
        "UPDATE acceptance_criteria SET validated = 1 WHERE workspace_id = ?",
        (workspace["id"],)
    )
    db.commit()
    db.close()

    commit_hash = _make_commit(workspace["working_dir"])

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={"commit_hash": commit_hash})
    assert code == 200
    assert result["phase"] == "4.0"


def test_last_commit_skips_criteria_when_not_last_subphase(workspace, project):
    """Non-last sub-phase commit skips criteria validation even with invalid criteria."""
    _setup_execution_phase(workspace["id"], "3.1.4", num_plan_phases=3)
    add_progress(workspace["id"], "3.1", "Sub-phase 1 complete")

    add_criterion(
        workspace["id"],
        cr_type="unit_test",
        status="accepted",
        details_json=json.dumps({"file": "tests/nonexistent_test.py", "test_names": ["test_foo"]}),
    )

    commit_hash = _make_commit(workspace["working_dir"])

    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"], body={"commit_hash": commit_hash})
    assert code == 200
    assert result["phase"] == "3.2.0"


# ── Plan approval gate with criteria status ─────────────────────────────────


def test_approve_blocked_by_proposed_criteria(client, workspace):
    """Plan approval at 2.1 is blocked when a criterion has 'rejected' status."""
    plan = make_plan_json(1)
    set_phase(workspace["id"], "2.1", gate_nonce="nonce-prop", plan_json=plan, plan_status="approved")
    add_criterion(workspace["id"], status="rejected")

    r = client.post("/api/ws/test-project/feature/test/approve", json={"token": "nonce-prop"})
    assert r.status_code == 400
    assert "acceptance criteria" in r.json["error"].lower()


def test_approve_gate_blocked_by_unresolved_review(client, workspace, project):
    """approve_gate blocked when unresolved review items exist."""
    plan = make_plan_json(2)
    set_phase(workspace["id"], "3.1.3",
              plan_json=plan, plan_status="approved", scope_status="approved",
              gate_nonce="test-nonce")
    add_comment(workspace["id"], scope="review", text="Unresolved finding", resolution="open")
    r = client.post(
        f"/api/ws/{project['id']}/{workspace['branch']}/approve",
        json={"token": "test-nonce"}
    )
    assert r.status_code == 422
    data = r.get_json()
    assert "guard_errors" in data


def test_approve_gate_passes_with_resolved_review(client, workspace, project):
    """approve_gate passes when all review items are resolved."""
    from db import get_db
    plan = make_plan_json(2)
    set_phase(workspace["id"], "3.1.3",
              plan_json=plan, plan_status="approved", scope_status="approved",
              gate_nonce="test-nonce")
    comment_id = add_comment(workspace["id"], scope="review", text="Resolved finding", resolution="fixed")
    db = get_db()
    db.execute("UPDATE discussions SET status = 'resolved' WHERE id = ?", (comment_id,))
    db.commit()
    db.close()
    r = client.post(
        f"/api/ws/{project['id']}/{workspace['branch']}/approve",
        json={"token": "test-nonce"}
    )
    assert r.status_code == 200
