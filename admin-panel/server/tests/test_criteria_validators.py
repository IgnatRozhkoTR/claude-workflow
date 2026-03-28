import json

import pytest

from advance.validators import validate_criterion, validate_all


def _make_criterion(cr_type, details=None):
    return {
        "id": 1,
        "type": cr_type,
        "description": "Test",
        "details_json": json.dumps(details) if details is not None else None,
    }


def test_unit_test_file_exists(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_service.py").write_text("def test_create(): pass\ndef test_delete(): pass\n")
    criterion = _make_criterion("unit_test", {"file": "tests/test_service.py"})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert passed


def test_unit_test_file_missing(tmp_path):
    criterion = _make_criterion("unit_test", {"file": "tests/nonexistent.py"})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert not passed
    assert "not found" in msg


def test_unit_test_all_methods_present(tmp_path):
    (tmp_path / "test_file.py").write_text("def test_create():\n    pass\ndef test_update():\n    pass\n")
    criterion = _make_criterion("unit_test", {"file": "test_file.py", "test_names": ["test_create", "test_update"]})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert passed


def test_unit_test_missing_method(tmp_path):
    (tmp_path / "test_file.py").write_text("def test_create():\n    pass\n")
    criterion = _make_criterion("unit_test", {"file": "test_file.py", "test_names": ["test_create", "test_missing"]})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert not passed
    assert "test_missing" in msg


def test_unit_test_no_file_specified(tmp_path):
    criterion = _make_criterion("unit_test", {})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert not passed


def test_integration_test_delegates_to_unit(tmp_path):
    (tmp_path / "test_it.py").write_text("def test_integration(): pass\n")
    criterion = _make_criterion("integration_test", {"file": "test_it.py"})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert passed


def test_bdd_scenario_pass(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "login.feature").write_text(
        "Feature: Login\n\n  Scenario: Valid login\n    Given a user\n"
    )
    criterion = _make_criterion("bdd_scenario", {"file": "features/login.feature", "scenario_names": ["Valid login"]})
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert passed


def test_bdd_scenario_missing(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "login.feature").write_text("Feature: Login\n\n  Scenario: Valid login\n")
    criterion = _make_criterion(
        "bdd_scenario",
        {"file": "features/login.feature", "scenario_names": ["Valid login", "Missing scenario"]},
    )
    passed, msg = validate_criterion(criterion, str(tmp_path))
    assert not passed


def test_custom_not_auto_validated(tmp_path, clean_db):
    """validate_all must not auto-pass custom criteria; unvalidated custom criteria cause all_passed=False."""
    from core.db import get_db
    from testing_utils import add_criterion

    db = get_db()
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES ('p2', 'P2', '/tmp/p2', '2024-01-01')"
    )
    db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, created, phase) "
        "VALUES ('p2', 'b2', 'b2', ?, '2024-01-01', '0')",
        (str(tmp_path),),
    )
    ws_id = db.execute("SELECT id FROM workspaces WHERE project_id = 'p2'").fetchone()["id"]
    db.execute(
        "INSERT INTO acceptance_criteria (workspace_id, type, description, details_json, source, status, created_at) "
        "VALUES (?, 'custom', 'Manual check', NULL, 'user', 'accepted', '2024-01-01')",
        (ws_id,),
    )
    db.commit()

    all_passed, results = validate_all(db, ws_id, str(tmp_path))
    db.close()

    assert not all_passed
    assert len(results) == 1
    assert not results[0]["passed"]
    assert "manual" in results[0]["message"].lower() or "approval" in results[0]["message"].lower()


def test_custom_manually_validated(tmp_path, clean_db):
    """A custom criterion with validated=1 must not appear in failed results; all_passed is True."""
    from core.db import get_db

    db = get_db()
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES ('p3', 'P3', '/tmp/p3', '2024-01-01')"
    )
    db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, created, phase) "
        "VALUES ('p3', 'b3', 'b3', ?, '2024-01-01', '0')",
        (str(tmp_path),),
    )
    ws_id = db.execute("SELECT id FROM workspaces WHERE project_id = 'p3'").fetchone()["id"]
    db.execute(
        "INSERT INTO acceptance_criteria (workspace_id, type, description, details_json, source, status, validated, created_at) "
        "VALUES (?, 'custom', 'Manual check', NULL, 'user', 'accepted', 1, '2024-01-01')",
        (ws_id,),
    )
    db.commit()

    all_passed, results = validate_all(db, ws_id, str(tmp_path))
    db.close()

    assert all_passed
    assert len(results) == 0


def test_validate_all_mixed(tmp_path, clean_db):
    """validate_all returns correct per-criterion results when some pass and some fail."""
    (tmp_path / "test_ok.py").write_text("def test_one(): pass\n")

    from core.db import get_db
    from testing_utils import add_criterion

    db = get_db()
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES ('p', 'P', '/tmp/p', '2024-01-01')"
    )
    db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, created, phase) "
        "VALUES ('p', 'b', 'b', ?, '2024-01-01', '0')",
        (str(tmp_path),),
    )
    ws_id = db.execute("SELECT id FROM workspaces WHERE project_id = 'p'").fetchone()["id"]
    db.execute(
        "INSERT INTO acceptance_criteria (workspace_id, type, description, details_json, source, status, created_at) "
        "VALUES (?, 'unit_test', 'Good', ?, 'user', 'accepted', '2024-01-01')",
        (ws_id, json.dumps({"file": "test_ok.py"})),
    )
    db.execute(
        "INSERT INTO acceptance_criteria (workspace_id, type, description, details_json, source, status, created_at) "
        "VALUES (?, 'unit_test', 'Bad', ?, 'user', 'accepted', '2024-01-01')",
        (ws_id, json.dumps({"file": "nonexistent.py"})),
    )
    db.commit()

    all_passed, results = validate_all(db, ws_id, str(tmp_path))
    db.close()

    assert not all_passed
    assert len(results) == 2
    assert results[0]["passed"]
    assert not results[1]["passed"]
