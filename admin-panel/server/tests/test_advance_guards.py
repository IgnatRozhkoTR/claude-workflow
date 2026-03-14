"""Tests for cross-cutting advance guards."""
from advance_guards import GUARD_ORCHESTRATOR, ResearchProvenGuard, ReviewGuard
from advance_service import perform_advance
from testing_utils import set_phase, add_progress, add_research, make_plan_json, add_comment
from db import get_db


def _get_ws_row(ws_id):
    db = get_db()
    row = db.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    db.close()
    return row


# ── Guard unit tests (evaluate directly) ─────────────────────────────────────

def test_guard_skip_at_exempt_phase(workspace, project):
    """Guard returns 'skip' at exempt phases."""
    guard = ResearchProvenGuard()
    add_research(workspace["id"], topic="Unproven", proven=0)
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("0", ws, {})
    assert result["status"] == "skip"
    assert result["guard"] == "research_proven"


def test_guard_approved_no_research(workspace, project):
    """No research entries — guard approves."""
    guard = ResearchProvenGuard()
    set_phase(workspace["id"], "1.3")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("1.3", ws, {})
    assert result["status"] == "approved"


def test_guard_approved_all_proven(workspace, project):
    """All research proven — guard approves."""
    guard = ResearchProvenGuard()
    add_research(workspace["id"], topic="Good", proven=1)
    set_phase(workspace["id"], "1.3")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("1.3", ws, {})
    assert result["status"] == "approved"


def test_guard_rejected_unproven(workspace, project):
    """Unproven research — guard rejects."""
    guard = ResearchProvenGuard()
    add_research(workspace["id"], topic="Unproven", proven=0)
    set_phase(workspace["id"], "1.3")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("1.3", ws, {})
    assert result["status"] == "rejected"
    assert "unproven" in result


def test_guard_rejected_disproved(workspace, project):
    """Rejected research — guard rejects with rejected list."""
    guard = ResearchProvenGuard()
    add_research(workspace["id"], topic="Bad", proven=-1)
    set_phase(workspace["id"], "2.0")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("2.0", ws, {})
    assert result["status"] == "rejected"
    assert "rejected" in result
    assert len(result["rejected"]) == 1


# ── Orchestrator tests ───────────────────────────────────────────────────────

def test_orchestrator_collects_all_results(workspace, project):
    """Orchestrator returns results from all guards."""
    ws = _get_ws_row(workspace["id"])
    results = GUARD_ORCHESTRATOR.evaluate_all("0", ws, {})
    assert isinstance(results, list)
    assert len(results) >= 1  # at least ResearchProvenGuard
    assert all("status" in r for r in results)


# ── Integration with perform_advance ─────────────────────────────────────────

def test_advance_blocked_by_guard_returns_errors_list(workspace, project):
    """perform_advance returns guard_errors list on rejection."""
    add_research(workspace["id"], topic="Unproven", proven=0)
    set_phase(workspace["id"], "1.3")
    add_progress(workspace["id"], "1.3", "Impact done")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422
    assert "guard_errors" in result
    assert isinstance(result["guard_errors"], list)
    assert any(e["guard"] == "research_proven" for e in result["guard_errors"])


def test_advance_passes_guards_when_all_approved(workspace, project):
    """perform_advance succeeds when all guards approve."""
    add_research(workspace["id"], topic="Good", proven=1)
    set_phase(workspace["id"], "1.3")
    add_progress(workspace["id"], "1.3", "Impact done")
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "2.0"


def test_advance_at_exempt_phase_ignores_unproven(workspace, project):
    """Guards returning 'skip' don't block advancement."""
    add_research(workspace["id"], topic="Unproven", proven=0)
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 200
    assert result["phase"] == "1.0"


# ── PlanApprovedGuard tests ──────────────────────────────────────────────────

def test_plan_guard_skip_early_phases(workspace, project):
    """Plan guard skips at phases before planning."""
    from advance_guards import PlanApprovedGuard
    guard = PlanApprovedGuard()
    ws = _get_ws_row(workspace["id"])
    for phase in ("0", "1.0", "1.1", "1.2", "1.3"):
        result = guard.evaluate(phase, ws, {})
        assert result["status"] == "skip", f"Expected skip at phase {phase}"


def test_plan_guard_approved_no_plan(workspace, project):
    """No plan exists — guard approves (nothing to check)."""
    from advance_guards import PlanApprovedGuard
    guard = PlanApprovedGuard()
    set_phase(workspace["id"], "2.0")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("2.0", ws, {})
    assert result["status"] == "approved"


def test_plan_guard_rejected_unapproved(workspace, project):
    """Plan exists but not approved — guard rejects."""
    from advance_guards import PlanApprovedGuard
    guard = PlanApprovedGuard()
    plan = make_plan_json(1)
    set_phase(workspace["id"], "2.0", plan_json=plan, plan_status="pending")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("2.0", ws, {})
    assert result["status"] == "rejected"
    assert result["guard"] == "plan_approved"


def test_plan_guard_approved_when_approved(workspace, project):
    """Plan approved — guard passes."""
    from advance_guards import PlanApprovedGuard
    guard = PlanApprovedGuard()
    plan = make_plan_json(1)
    set_phase(workspace["id"], "2.0", plan_json=plan, plan_status="approved")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("2.0", ws, {})
    assert result["status"] == "approved"


# ── ScopeApprovedGuard tests ────────────────────────────────────────────────

def test_scope_guard_skip_non_execution(workspace, project):
    """Scope guard skips at non-execution phases."""
    from advance_guards import ScopeApprovedGuard
    guard = ScopeApprovedGuard()
    ws = _get_ws_row(workspace["id"])
    for phase in ("0", "1.0", "1.1", "2.0", "2.1", "5"):
        result = guard.evaluate(phase, ws, {})
        assert result["status"] == "skip", f"Expected skip at phase {phase}"


def test_scope_guard_rejected_unapproved(workspace, project):
    """Scope not approved during execution — guard rejects."""
    from advance_guards import ScopeApprovedGuard
    guard = ScopeApprovedGuard()
    set_phase(workspace["id"], "3.1.0", scope_status="pending")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("3.1.0", ws, {})
    assert result["status"] == "rejected"
    assert result["guard"] == "scope_approved"


def test_scope_guard_approved_when_approved(workspace, project):
    """Scope approved during execution — guard passes."""
    from advance_guards import ScopeApprovedGuard
    guard = ScopeApprovedGuard()
    set_phase(workspace["id"], "3.1.0", scope_status="approved")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("3.1.0", ws, {})
    assert result["status"] == "approved"



def test_set_plan_revokes_scope_status(workspace, project):
    """workspace_set_plan should revoke both plan_status and scope_status."""
    set_phase(workspace["id"], "2.0", scope_status="approved")
    db = get_db()
    try:
        plan_json = '{"description":"test","systemDiagram":"","execution":[{"id":"3.1","name":"Test","scope":{"must":["src/"],"may":[]},"tasks":[]}]}'
        db.execute("UPDATE workspaces SET plan_json = ?, plan_status = 'pending', scope_status = 'pending' WHERE id = ?",
                   (plan_json, workspace["id"]))
        db.commit()
    finally:
        db.close()
    ws = _get_ws_row(workspace["id"])
    assert ws["plan_status"] == "pending"
    assert ws["scope_status"] == "pending"


# ── ReviewGuard tests ────────────────────────────────────────────────────────

def test_review_guard_skip_at_exempt_phases(workspace, project):
    """Review guard skips at pre-implementation and review-creation phases."""
    guard = ReviewGuard()
    # Add an unresolved review comment — should still skip at exempt phases
    add_comment(workspace["id"], scope="review", text="Unresolved finding", resolution="open")
    ws = _get_ws_row(workspace["id"])
    for phase in ("0", "1.0", "1.1", "1.2", "1.3", "2.0", "2.1", "4.0"):
        result = guard.evaluate(phase, ws, {})
        assert result["status"] == "skip", f"Expected skip at phase {phase}"


def test_review_guard_approved_no_items(workspace, project):
    """No review items — guard approves."""
    guard = ReviewGuard()
    set_phase(workspace["id"], "3.1.0")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("3.1.0", ws, {})
    assert result["status"] == "approved"


def test_review_guard_rejected_open_comments(workspace, project):
    """Unresolved review comments — guard rejects."""
    guard = ReviewGuard()
    add_comment(workspace["id"], scope="review", text="Open finding", resolution="open")
    set_phase(workspace["id"], "3.1.1")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("3.1.1", ws, {})
    assert result["status"] == "rejected"
    assert result["unresolved_count"] == 1


def test_review_guard_approved_all_resolved(workspace, project):
    """All review items resolved — guard approves."""
    guard = ReviewGuard()
    from db import get_db
    comment_id = add_comment(workspace["id"], scope="review", text="Fixed finding", resolution="fixed")
    db = get_db()
    db.execute("UPDATE discussions SET status = 'resolved' WHERE id = ?", (comment_id,))
    db.commit()
    db.close()
    set_phase(workspace["id"], "4.1")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("4.1", ws, {})
    assert result["status"] == "approved"


def test_review_guard_rejects_at_execution_phase(workspace, project):
    """Guard blocks at execution phases (3.N.K) when review items are open."""
    guard = ReviewGuard()
    add_comment(workspace["id"], scope="review", text="Blocking comment")
    set_phase(workspace["id"], "3.1.2")
    ws = _get_ws_row(workspace["id"])
    result = guard.evaluate("3.1.2", ws, {})
    assert result["status"] == "rejected"


def test_advance_blocked_by_review_guard(workspace, project):
    """perform_advance blocked by ReviewGuard with unresolved review item."""
    add_comment(workspace["id"], scope="review", text="Blocking finding", resolution="open")
    set_phase(workspace["id"], "4.1", scope_status="approved", plan_status="approved")
    add_progress(workspace["id"], "4", "Fixes done")
    add_research(workspace["id"], topic="Good", proven=1)
    ws = _get_ws_row(workspace["id"])
    result, code = perform_advance(ws, project["path"])
    assert code == 422
    assert "guard_errors" in result
    assert any(e["guard"] == "review_resolved" for e in result["guard_errors"])
