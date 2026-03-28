from mcp_tools import mcp, with_mcp_workspace
from core.helpers import VALID_CRITERIA_TYPES
from core.i18n import t
from services import criteria_service


@mcp.tool()
@with_mcp_workspace
def workspace_propose_criteria(ws, project, db, locale, type: str, description: str, details_json: str = "") -> dict:
    """Propose an acceptance criterion for the workspace. Called by the agent to suggest verifiable criteria.

    - type: one of 'unit_test', 'integration_test', 'bdd_scenario', 'custom'
    - description: human-readable description of what must pass
    - details_json: optional JSON string with type-specific details
      For unit_test/integration_test: {"file": "path/to/TestFile.java", "test_names": ["testMethod1", "testMethod2"]}
      For bdd_scenario: {"file": "features/file.feature", "scenario_names": ["scenario1"]}
      For custom: {"instruction": "description of what to verify"}
      All types support an optional "verification_command" field — a shell command the server runs at commit time. Exit 0 = pass, non-zero = fail.

    Proposed criteria are visible in the admin panel where the user can accept or reject them."""
    if type not in VALID_CRITERIA_TYPES:
        return {"error": t("mcp.error.invalidCriteriaType", locale, type=type, valid_types=", ".join(VALID_CRITERIA_TYPES))}

    result = criteria_service.propose_criterion(
        db, ws["id"], type, description, details_json=details_json or None, source="agent"
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_criteria(ws, project, db, locale, status: str = "", type: str = "") -> list:
    """Get acceptance criteria for the current workspace, optionally filtered.

    - status: filter by status ('proposed', 'accepted', 'rejected'). Empty = all.
    - type: filter by type ('unit_test', 'integration_test', 'bdd_scenario', 'custom'). Empty = all.

    Returns list of criteria with id, type, description, details, source, status, validated, validation_message."""
    return criteria_service.get_criteria(
        db, ws["id"], status=status or None, criterion_type=type or None
    )


@mcp.tool()
@with_mcp_workspace
def workspace_update_criteria(ws, project, db, locale, criterion_id: int, description: str = "", details_json: str = "") -> dict:
    """Update an existing acceptance criterion's description and/or details. Use this to fill in
    file paths, test names, and refined descriptions for criteria created by the user.

    - criterion_id: ID of the criterion to update
    - description: updated description (optional, keeps existing if empty)
    - details_json: updated details JSON (optional, keeps existing if empty)
      For unit_test/integration_test: {"file": "path/to/TestFile.java", "test_names": ["testMethod1", "testMethod2"]}
      For bdd_scenario: {"file": "features/file.feature", "scenario_names": ["scenario1"]}
      For custom: {"instruction": "description of what to verify"}
    """
    result = criteria_service.update_criterion(
        db, criterion_id, ws["id"],
        description=description or None, details_json=details_json or None
    )
    if "error" in result:
        error_key = result["error"]
        if error_key == "criterion_not_found":
            return {"error": t("mcp.error.criterionNotFound", locale, criterion_id=criterion_id)}
        if error_key == "cannot_update_accepted":
            return {"error": t("mcp.error.cannotUpdateAcceptedCriteria", locale)}
        if error_key == "nothing_to_update":
            return {"error": t("mcp.error.nothingToUpdate", locale)}
        return result
    db.commit()
    return result
