"""Programmatic validators for acceptance criteria.

Each validator checks if a specific type of acceptance criterion is fulfilled
by examining files in the working directory.
"""
import json, os, re
from pathlib import Path


def validate_criterion(criterion, working_dir):
    """Validate a single acceptance criterion. Returns (passed: bool, message: str)."""
    cr_type = criterion["type"]
    details = json.loads(criterion["details_json"]) if criterion["details_json"] else {}
    
    validator = _VALIDATORS.get(cr_type)
    if not validator:
        return True, "No programmatic validator for this type"
    
    return validator(details, working_dir)


def validate_all(db, workspace_id, working_dir):
    """Validate all accepted criteria for a workspace. Returns (all_passed: bool, results: list)."""
    rows = db.execute(
        "SELECT id, type, description, details_json FROM acceptance_criteria "
        "WHERE workspace_id = ? AND status = 'accepted' AND type != 'custom' ORDER BY id",
        (workspace_id,)
    ).fetchall()
    
    results = []
    all_passed = True
    
    for row in rows:
        passed, message = validate_criterion(row, working_dir)
        validated = 1 if passed else -1
        
        db.execute(
            "UPDATE acceptance_criteria SET validated = ?, validation_message = ? WHERE id = ?",
            (validated, message, row["id"])
        )
        
        results.append({
            "id": row["id"],
            "type": row["type"],
            "description": row["description"],
            "passed": passed,
            "message": message,
        })
        
        if not passed:
            all_passed = False
    
    db.commit()

    custom_unvalidated = db.execute(
        "SELECT id, type, description FROM acceptance_criteria "
        "WHERE workspace_id = ? AND status = 'accepted' AND type = 'custom' AND validated != 1",
        (workspace_id,)
    ).fetchall()
    for row in custom_unvalidated:
        results.append({
            "id": row["id"],
            "type": "custom",
            "description": row["description"],
            "passed": False,
            "message": "Awaiting manual user approval via admin panel",
        })
        all_passed = False

    return all_passed, results


def _validate_file_contains(details, working_dir, file_key, names_key, file_label, names_label):
    """Generic validator: check a file exists and contains expected names."""
    file_path = details.get(file_key, "").strip()
    names = details.get(names_key, [])

    if not file_path:
        return False, f"No {file_label.lower()} specified in details"

    full_path = Path(working_dir) / file_path if working_dir else Path(file_path)
    if not full_path.exists():
        return False, f"{file_label} not found: {file_path}"

    if not names:
        return True, f"{file_label} exists: {file_path}"

    content = full_path.read_text()
    missing = [n for n in names if n not in content]
    if missing:
        return False, f"Missing {names_label.lower()} in {file_path}: {', '.join(missing)}"

    return True, f"All {len(names)} {names_label.lower()} found in {file_path}"


def _validate_unit_test(details, working_dir):
    return _validate_file_contains(details, working_dir, "file", "test_names", "Test file", "Tests")


def _validate_integration_test(details, working_dir):
    return _validate_unit_test(details, working_dir)


def _validate_bdd_scenario(details, working_dir):
    return _validate_file_contains(details, working_dir, "file", "scenario_names", "Feature file", "Scenarios")


_VALIDATORS = {
    "unit_test": _validate_unit_test,
    "integration_test": _validate_integration_test,
    "bdd_scenario": _validate_bdd_scenario,
}
