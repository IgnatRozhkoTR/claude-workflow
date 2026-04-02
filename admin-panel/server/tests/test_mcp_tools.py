"""Tests for MCP tool functions in mcp_server.py.

Import mcp_server functions inside test functions — mcp_server calls init_db() on import,
so the import must happen after setup_db (session autouse) patches DB_PATH.
"""
import json
import os
from pathlib import Path

from testing_utils import (
    set_phase, add_progress, add_research, add_comment,
    add_criterion, make_plan_json, _git
)


class TestGetState:
    def test_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_get_state
        result = workspace_get_state()
        assert "error" in result

    def test_basic_state(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_state
        result = workspace_get_state()
        assert result["phase"] == "0"
        assert result["scope"] == {"must": [], "may": []}

    def test_full_state_with_data(self, workspace, monkeypatch):
        add_research(workspace["id"])
        add_comment(workspace["id"])
        add_progress(workspace["id"], "1.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_state
        result = workspace_get_state()
        assert len(result["research_summary"]) == 1
        assert "1.0" in result["progress_summary"]

    def test_state_includes_branch_and_working_dir(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_state
        result = workspace_get_state()
        assert result["branch"] == workspace["branch"]
        assert result["working_dir"] == workspace["working_dir"]

    def test_state_no_gate_nonce(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_state
        result = workspace_get_state()
        assert "gate_nonce" not in result

    def test_state_empty_collections(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_state
        result = workspace_get_state()
        assert result["research_summary"] == []
        assert result["unresolved_comments_count"] == 0
        assert result["review_issues_summary"] == {}
        assert result["criteria_summary"] == {}
        assert result["previous_sessions_count"] == 0


class TestAdvance:
    def test_advance_from_0(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_advance
        result = workspace_advance()
        assert result["phase"] == "1.0"

    def test_advance_blocked(self, workspace, monkeypatch):
        set_phase(workspace["id"], "1.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_advance
        result = workspace_advance()
        assert "blocked" in result.get("status", "") or "message" in result

    def test_advance_at_user_gate(self, workspace, monkeypatch):
        set_phase(workspace["id"], "2.1")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_advance
        result = workspace_advance()
        assert "error" in result

    def test_advance_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_advance
        result = workspace_advance()
        assert "error" in result


class TestSetScope:
    def test_set_scope_during_planning(self, workspace, monkeypatch):
        set_phase(workspace["id"], "2.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_scope
        result = workspace_set_scope(scope={"3.1": {"must": ["src/"], "may": ["tests/"]}})
        assert result["ok"]

    def test_set_scope_during_execution_revokes_approval(self, workspace, monkeypatch):
        set_phase(workspace["id"], "3.1.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_scope, workspace_get_state
        scope = {"3.1": {"must": ["src/new/"], "may": ["test/"]}}
        result = workspace_set_scope(scope=scope)
        assert result["ok"] is True
        assert result["scope_status"] == "pending"
        state = workspace_get_state()
        assert state["scope"] == scope
        assert state["scope_status"] == "pending"

    def test_set_scope_blocked_at_early_phase(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_scope
        result = workspace_set_scope(scope={"3.1": {"must": ["src/"]}})
        assert "error" in result

    def test_set_scope_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_set_scope
        result = workspace_set_scope(scope={"3.1": {"must": ["src/"]}})
        assert "error" in result

    def test_set_scope_persisted(self, workspace, monkeypatch):
        set_phase(workspace["id"], "2.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_scope, workspace_get_state
        scope = {"3.1": {"must": ["src/"], "may": ["docs/"]}}
        workspace_set_scope(scope=scope)
        state = workspace_get_state()
        assert state["scope"] == scope


class TestSetPlan:
    def test_set_plan_success(self, workspace, monkeypatch):
        set_phase(workspace["id"], "2.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_plan
        plan = {
            "systemDiagram": "",
            "execution": [
                {
                    "id": "3.1",
                    "name": "Phase 1",
                    "scope": {"must": ["src/"]},
                    "tasks": [],
                }
            ],
        }
        result = workspace_set_plan(plan=plan)
        assert result["ok"]

    def test_set_plan_blocked_early(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_plan
        result = workspace_set_plan(plan={})
        assert "error" in result

    def test_set_plan_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_set_plan
        result = workspace_set_plan(plan={})
        assert "error" in result

    def test_set_plan_persisted(self, workspace, monkeypatch):
        set_phase(workspace["id"], "2.0")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_set_plan, workspace_get_plan
        plan = {"systemDiagram": "graph LR", "execution": []}
        workspace_set_plan(plan=plan)
        full_plan = workspace_get_plan()
        assert full_plan["systemDiagram"] == "graph LR"


class TestDiscussions:
    def test_post_discussion(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_post_discussion
        result = workspace_post_discussion(topic="Should we use X?")
        assert result["ok"]
        assert result["discussion_id"]

    def test_post_discussion_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_post_discussion
        result = workspace_post_discussion(topic="Test")
        assert "error" in result

    def test_post_discussion_no_context(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_post_discussion
        result = workspace_post_discussion(topic="Async vs sync approach")
        assert result["ok"]
        assert result["discussion_id"]

    def test_post_discussion_visible_in_state(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_post_discussion, workspace_get_state
        workspace_post_discussion(topic="Architecture decision")
        state = workspace_get_state()
        assert len(state["discussions"]) == 1
        assert state["discussions"][0]["text"] == "Architecture decision"


class TestResearch:
    def test_save_research(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_save_research
        findings = [
            {
                "summary": "Found X",
                "details": "Details",
                "proof": {
                    "type": "web",
                    "url": "http://example.com",
                    "title": "Title",
                    "quote": "Quote",
                },
            }
        ]
        result = workspace_save_research(topic="Auth flow", findings=findings)
        assert result["ok"]
        assert result["research_id"]

    def test_save_research_empty_findings(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_save_research
        result = workspace_save_research(topic="Empty", findings=[])
        assert "error" in result

    def test_save_research_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_save_research
        result = workspace_save_research(topic="Test", findings=[{"summary": "x"}])
        assert "error" in result

    def test_save_research_with_code_proof_enrichment(self, workspace, monkeypatch):
        Path(workspace["working_dir"]).joinpath("src").mkdir(exist_ok=True)
        Path(workspace["working_dir"]).joinpath("src/service.py").write_text(
            "line1\nline2\nline3\nline4\nline5\n"
        )
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_save_research
        findings = [
            {
                "summary": "Found pattern",
                "proof": {
                    "type": "code",
                    "file": "src/service.py",
                    "line_start": 1,
                    "line_end": 5,
                    "snippet_start": 2,
                    "snippet_end": 4,
                },
            }
        ]
        result = workspace_save_research(topic="Code analysis", findings=findings)
        assert result["ok"]

    def test_list_research(self, workspace, monkeypatch):
        add_research(workspace["id"], topic="Topic 1")
        add_research(workspace["id"], topic="Topic 2")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_list_research
        result = workspace_list_research()
        assert len(result) == 2

    def test_list_research_empty(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_list_research
        result = workspace_list_research()
        assert result == []

    def test_get_research_by_ids(self, workspace, monkeypatch):
        rid = add_research(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_research
        result = workspace_get_research(ids=[rid])
        assert len(result) == 1
        assert result[0]["id"] == rid

    def test_get_research_empty_ids(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_research
        result = workspace_get_research(ids=[])
        assert result == []

    def test_get_research_unknown_id(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_research
        result = workspace_get_research(ids=[9999])
        assert result == []

    def test_prove_research(self, workspace, monkeypatch):
        rid = add_research(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_prove_research
        result = workspace_prove_research(id=rid, proven=True, notes="Verified")
        assert result["ok"]
        assert result["proven"] is True

    def test_prove_research_not_found(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_prove_research
        result = workspace_prove_research(id=9999, proven=True)
        assert "error" in result

    def test_prove_research_rejected(self, workspace, monkeypatch):
        rid = add_research(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_prove_research
        result = workspace_prove_research(id=rid, proven=False, notes="Could not verify")
        assert result["ok"]
        assert result["proven"] is False

    def test_save_research_with_summary(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_save_research, workspace_list_research, workspace_get_research
        findings = [
            {
                "summary": "Found pattern",
                "proof": {"type": "web", "url": "http://example.com", "title": "T", "quote": "Q"},
            }
        ]
        result = workspace_save_research(
            topic="Summary test", findings=findings, summary="Overall this research found a pattern."
        )
        assert result["ok"]
        rid = result["research_id"]

        listed = workspace_list_research()
        entry = next(e for e in listed if e["id"] == rid)
        assert entry["summary"] == "Overall this research found a pattern."

        full = workspace_get_research(ids=[rid])
        assert full[0]["summary"] == "Overall this research found a pattern."

    def test_save_research_without_summary(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_save_research, workspace_list_research, workspace_get_research
        findings = [
            {
                "summary": "Found something",
                "proof": {"type": "web", "url": "http://example.com", "title": "T", "quote": "Q"},
            }
        ]
        result = workspace_save_research(topic="No summary test", findings=findings)
        assert result["ok"]
        rid = result["research_id"]

        listed = workspace_list_research()
        entry = next(e for e in listed if e["id"] == rid)
        assert entry["summary"] is None

        full = workspace_get_research(ids=[rid])
        assert full[0]["summary"] is None

    def test_save_research_normalizes_paths(self, workspace, monkeypatch, tmp_path):
        # Simulate agent running from a subdirectory
        subdir = Path(workspace["working_dir"]) / "src"
        subdir.mkdir(exist_ok=True)
        (subdir / "main.py").write_text("x = 1\n" * 20)
        monkeypatch.chdir(str(subdir))

        from mcp_server import workspace_save_research
        result = workspace_save_research(
            topic="Path test",
            findings=[{
                "summary": "Found something",
                "proof": {
                    "type": "code",
                    "file": "main.py",  # relative to cwd (src/), not working_dir
                    "line_start": 1,
                    "line_end": 5,
                }
            }]
        )
        assert result["ok"]

        # Verify the stored path is relative to working_dir, not cwd
        from mcp_server import workspace_get_research
        entries = workspace_get_research(ids=[result["research_id"]])
        assert entries[0]["findings"][0]["proof"]["file"] == "src/main.py"


class TestComments:
    def test_get_comments_empty(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_comments
        result = workspace_get_comments()
        assert result == []

    def test_get_comments_filtered(self, workspace, monkeypatch):
        add_comment(workspace["id"], scope="review", text="Review comment")
        add_comment(workspace["id"], scope="phase", text="Phase comment")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_comments
        result = workspace_get_comments(scope="review", unresolved_only=False)
        assert len(result) == 1
        assert result[0]["scope"] == "review"

    def test_get_comments_unresolved_only_default(self, workspace, monkeypatch):
        cid = add_comment(workspace["id"])
        from core.db import get_db
        db = get_db()
        db.execute("UPDATE discussions SET status = 'resolved' WHERE id = ?", (cid,))
        db.commit()
        db.close()
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_comments
        result = workspace_get_comments()
        assert result == []

    def test_resolve_comment(self, workspace, monkeypatch):
        cid = add_comment(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_comment
        result = workspace_resolve_comment(comment_id=cid)
        assert result["ok"]

    def test_resolve_comment_not_found(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_comment
        result = workspace_resolve_comment(comment_id=9999)
        assert "error" in result

    def test_resolve_comment_marks_resolved(self, workspace, monkeypatch):
        cid = add_comment(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_comment, workspace_get_comments
        workspace_resolve_comment(comment_id=cid)
        result = workspace_get_comments(unresolved_only=True)
        assert result == []


class TestReviewIssues:
    def test_submit_review_issue(self, workspace, monkeypatch):
        Path(workspace["working_dir"]).joinpath("src").mkdir(exist_ok=True)
        Path(workspace["working_dir"]).joinpath("src/main.py").write_text(
            "def main():\n    pass\n    return\n"
        )
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_submit_review_issue
        result = workspace_submit_review_issue(
            file_path="src/main.py",
            line_start=1,
            line_end=3,
            severity="critical",
            description="Dead code",
        )
        assert result["ok"]

    def test_submit_review_issue_with_codex_author(self, workspace, monkeypatch):
        Path(workspace["working_dir"]).joinpath("src").mkdir(exist_ok=True)
        Path(workspace["working_dir"]).joinpath("src/main.py").write_text(
            "def main():\n    pass\n"
        )
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_submit_review_issue, workspace_get_review_issues
        result = workspace_submit_review_issue(
            file_path="src/main.py",
            line_start=1,
            line_end=2,
            severity="major",
            description="Codex finding",
            reviewer_name="codex",
        )
        assert result["ok"]

        issues = workspace_get_review_issues()
        assert issues[0]["author"] == "codex"

    def test_submit_issue_file_not_found(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_submit_review_issue
        result = workspace_submit_review_issue(
            file_path="nonexistent.py",
            line_start=1,
            line_end=1,
            severity="major",
            description="Test",
        )
        assert "error" in result

    def test_submit_issue_invalid_severity(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_submit_review_issue
        result = workspace_submit_review_issue(
            file_path="any.py",
            line_start=1,
            line_end=1,
            severity="minor",
            description="Test",
        )
        assert "error" in result

    def test_submit_issue_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_submit_review_issue
        result = workspace_submit_review_issue(
            file_path="file.py",
            line_start=1,
            line_end=1,
            severity="critical",
            description="Test",
        )
        assert "error" in result

    def test_get_review_issues(self, workspace, monkeypatch):
        add_comment(
            workspace["id"], scope="review", text="Test issue", resolution="open",
            file_path="src/main.py", line_start=1, line_end=3
        )
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_review_issues
        result = workspace_get_review_issues()
        assert len(result) == 1
        issue = result[0]
        assert "description" in issue
        assert "resolution" in issue
        assert "author" in issue
        assert "resolved" in issue

    def test_get_review_issues_filtered(self, workspace, monkeypatch):
        add_comment(
            workspace["id"], scope="review", text="Open issue", resolution="open",
            file_path="src/main.py", line_start=1, line_end=3
        )
        add_comment(
            workspace["id"], scope="review", text="Fixed issue", resolution="fixed",
            file_path="src/main.py", line_start=5, line_end=7
        )
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_review_issues
        result = workspace_get_review_issues(status="open")
        assert len(result) == 1
        result2 = workspace_get_review_issues(status="fixed")
        assert len(result2) == 1
        result3 = workspace_get_review_issues(status="out_of_scope")
        assert len(result3) == 0

    def test_resolve_review_issue(self, workspace, monkeypatch):
        iid = add_comment(workspace["id"], scope="review", text="Test issue", resolution="open")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_review_issue
        result = workspace_resolve_review_issue(issue_id=iid, resolution="fixed")
        assert result["ok"]

    def test_resolve_issue_invalid_resolution(self, workspace, monkeypatch):
        iid = add_comment(workspace["id"], scope="review", text="Test issue", resolution="open")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_review_issue
        result = workspace_resolve_review_issue(issue_id=iid, resolution="wontfix")
        assert "error" in result

    def test_resolve_issue_not_found(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_review_issue
        result = workspace_resolve_review_issue(issue_id=9999, resolution="fixed")
        assert "error" in result

    def test_resolve_false_positive(self, workspace, monkeypatch):
        iid = add_comment(workspace["id"], scope="review", text="Test issue", resolution="open")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_review_issue
        result = workspace_resolve_review_issue(issue_id=iid, resolution="false_positive")
        assert result["ok"]
        assert result["resolution"] == "false_positive"

    def test_resolve_comment_blocked_for_review_scope(self, workspace, monkeypatch):
        cid = add_comment(workspace["id"], scope="review", text="Review finding", resolution="open")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_resolve_comment
        result = workspace_resolve_comment(comment_id=cid)
        assert "error" in result


class TestProgress:
    def test_update_progress_new(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_progress
        result = workspace_update_progress(phase="1.0", summary="Done assessment")
        assert result["ok"]

    def test_update_progress_existing(self, workspace, monkeypatch):
        add_progress(workspace["id"], "1.0", "Initial")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_progress
        result = workspace_update_progress(phase="1.0", summary="Updated")
        assert result["ok"]
        from core.db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT * FROM progress_entries WHERE workspace_id = ? AND phase = '1.0'",
            (workspace["id"],)
        ).fetchall()
        db.close()
        assert len(rows) == 1
        assert rows[0]["summary"] == "Updated"

    def test_update_progress_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_update_progress
        result = workspace_update_progress(phase="1.0", summary="Done")
        assert "error" in result

    def test_update_progress_visible_in_state(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_progress, workspace_get_state
        workspace_update_progress(phase="1.0", summary="Completed assessment phase")
        state = workspace_get_state()
        assert "1.0" in state["progress_summary"]
        assert state["progress_summary"]["1.0"] == "Completed assessment phase"


class TestCriteria:
    def test_propose_criteria(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_propose_criteria
        result = workspace_propose_criteria(type="unit_test", description="Test user service")
        assert result["ok"]
        assert result["criterion"]["source"] == "agent"
        assert result["criterion"]["status"] == "proposed"

    def test_propose_criteria_with_valid_details_json(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_propose_criteria, workspace_get_criteria
        details = json.dumps({"file": "tests/test_user.py", "test_names": ["test_create_user"]})
        result = workspace_propose_criteria(
            type="unit_test", description="User creation test", details_json=details
        )
        assert result["ok"]
        assert result["criterion"]["details"] == {"file": "tests/test_user.py", "test_names": ["test_create_user"]}

        criteria = workspace_get_criteria()
        match = next(c for c in criteria if c["id"] == result["criterion"]["id"])
        assert match["details"] == {"file": "tests/test_user.py", "test_names": ["test_create_user"]}

    def test_propose_criteria_with_invalid_details_json(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_propose_criteria
        result = workspace_propose_criteria(
            type="unit_test", description="Bad JSON", details_json="{not valid json"
        )
        assert "error" in result
        assert "not valid JSON" in result["error"]

    def test_propose_criteria_with_non_object_details_json(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_propose_criteria
        result = workspace_propose_criteria(
            type="unit_test", description="String details", details_json='"just a string"'
        )
        assert "error" in result
        assert "object" in result["error"].lower()

    def test_propose_criteria_invalid_type(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_propose_criteria
        result = workspace_propose_criteria(type="invalid_type", description="Test")
        assert "error" in result

    def test_propose_criteria_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        from mcp_server import workspace_propose_criteria
        result = workspace_propose_criteria(type="unit_test", description="Test")
        assert "error" in result

    def test_propose_all_valid_types(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_propose_criteria
        for cr_type in ("unit_test", "integration_test", "bdd_scenario", "custom"):
            result = workspace_propose_criteria(type=cr_type, description=f"Test {cr_type}")
            assert result["ok"], f"Expected ok for type {cr_type}"

    def test_get_criteria(self, workspace, monkeypatch):
        add_criterion(workspace["id"], status="accepted")
        add_criterion(workspace["id"], status="proposed")
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_criteria
        result = workspace_get_criteria()
        assert len(result) == 2
        result2 = workspace_get_criteria(status="accepted")
        assert len(result2) == 1

    def test_get_criteria_empty(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_get_criteria
        result = workspace_get_criteria()
        assert result == []

    def test_update_criteria(self, workspace, monkeypatch):
        cid = add_criterion(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_criteria
        result = workspace_update_criteria(
            criterion_id=cid,
            description="Updated desc",
            details_json='{"file": "test.py"}',
        )
        assert result["ok"]
        assert result["criterion"]["description"] == "Updated desc"

    def test_update_criteria_nothing(self, workspace, monkeypatch):
        cid = add_criterion(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_criteria
        result = workspace_update_criteria(criterion_id=cid)
        assert "error" in result

    def test_update_criteria_not_found(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_criteria
        result = workspace_update_criteria(criterion_id=9999, description="Updated")
        assert "error" in result

    def test_update_criteria_description_only(self, workspace, monkeypatch):
        cid = add_criterion(workspace["id"])
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_criteria
        result = workspace_update_criteria(criterion_id=cid, description="New description")
        assert result["ok"]
        assert result["criterion"]["description"] == "New description"

    def test_update_criteria_blocked_if_accepted(self, workspace, monkeypatch):
        from testing_utils import add_criterion
        from core.db import get_db
        criterion_id = add_criterion(workspace["id"], cr_type="unit_test", description="Test")
        db = get_db()
        db.execute("UPDATE acceptance_criteria SET status = 'accepted' WHERE id = ?", (criterion_id,))
        db.commit()
        db.close()

        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_criteria
        result = workspace_update_criteria(criterion_id=criterion_id, description="New desc")
        assert "error" in result
        assert "accepted" in result["error"].lower()

    def test_update_criteria_resets_rejected_to_proposed(self, workspace, monkeypatch):
        from testing_utils import add_criterion
        from core.db import get_db
        criterion_id = add_criterion(workspace["id"], cr_type="unit_test", description="Test")
        db = get_db()
        db.execute("UPDATE acceptance_criteria SET status = 'rejected' WHERE id = ?", (criterion_id,))
        db.commit()
        db.close()

        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_criteria
        result = workspace_update_criteria(criterion_id=criterion_id, description="Fixed desc")
        assert result["ok"]
        assert result.get("status_reset") == "proposed"

        db = get_db()
        row = db.execute("SELECT status FROM acceptance_criteria WHERE id = ?", (criterion_id,)).fetchone()
        db.close()
        assert row["status"] == "proposed"


class TestUpdateVerificationProfile:
    def _create_profile(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_create_verification_profile
        result = workspace_create_verification_profile(
            name="Test Java", language="java", lsp_command="jdtls"
        )
        assert result["ok"]
        return result["id"]

    def test_update_lsp_command(self, workspace, monkeypatch):
        profile_id = self._create_profile(workspace, monkeypatch)
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_verification_profile
        from core.db import get_db
        result = workspace_update_verification_profile(profile_id=profile_id, lsp_command="bash")
        assert result["ok"]
        db = get_db()
        row = db.execute("SELECT lsp_command FROM verification_profiles WHERE id = ?", (profile_id,)).fetchone()
        db.close()
        assert row["lsp_command"] == "bash"

    def test_update_multiple_fields(self, workspace, monkeypatch):
        profile_id = self._create_profile(workspace, monkeypatch)
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_verification_profile
        from core.db import get_db
        result = workspace_update_verification_profile(
            profile_id=profile_id,
            lsp_command="bash",
            lsp_args='["-c", "JAVA_HOME=/usr/lib/jvm/java-17 exec jdtls"]'
        )
        assert result["ok"]
        db = get_db()
        row = db.execute(
            "SELECT lsp_command, lsp_args FROM verification_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        db.close()
        assert row["lsp_command"] == "bash"
        assert row["lsp_args"] == '["-c", "JAVA_HOME=/usr/lib/jvm/java-17 exec jdtls"]'

    def test_update_nonexistent_profile(self, workspace, monkeypatch):
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_verification_profile
        result = workspace_update_verification_profile(profile_id=9999, lsp_command="bash")
        assert result == {"error": "profile_not_found"}

    def test_update_no_fields(self, workspace, monkeypatch):
        profile_id = self._create_profile(workspace, monkeypatch)
        monkeypatch.chdir(workspace["working_dir"])
        from mcp_server import workspace_update_verification_profile
        result = workspace_update_verification_profile(profile_id=profile_id)
        assert result == {"error": "no_fields_to_update"}
