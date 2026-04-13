from mcp_tools import mcp, with_mcp_workspace
from core.i18n import t
from services import plan_service
from services import scope_service


@mcp.tool()
@with_mcp_workspace
def workspace_set_scope(ws, project, db, locale, scope: dict) -> dict:
    """Set workspace scope as a phase-keyed map. Allowed from phase 1 onwards.

    Setting scope automatically revokes approval — the user must review and re-approve
    the new scope in the admin panel before code edits are allowed.

    Format: {"3.1": {"must": ["src/models/"], "may": ["src/config/"]}, "3.2": {"must": [...], "may": [...]}}
    Each key is a sub-phase ID from the execution plan. 'must' directories MUST have changes for the phase to advance.
    'may' directories are permitted but not required."""
    result = scope_service.set_scope(db, ws, scope)
    if "error" not in result:
        if ws["yolo_mode"]:
            db.execute("UPDATE workspaces SET scope_status = 'approved' WHERE id = ?", (ws["id"],))
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_set_plan(ws, project, db, locale, plan: dict) -> dict:
    """Set the execution plan. Editable during and after planning (phase >= 2.0).

    The plan can be updated freely during planning. Once the user approves the plan
    in the admin panel, approval is revoked each time the plan is updated — the user
    must review and re-approve before the workflow can advance past planning.

    The previous plan is saved automatically — call workspace_restore_plan to revert
    if the new plan hasn't been approved yet.

    Expected format:
    {
        "description": "High-level plain text description of what this plan achieves",
        "systemDiagram": "mermaid diagram string or array of {title, diagram}",
        "execution": [
            {
                "id": "3.1",
                "name": "Sub-phase name",
                "tasks": [{"title": "...", "files": ["..."], "agent": "...", "status": "pending", "group": "optional group name"}]
            }
        ]
    }

    Tasks with the same "group" name run in parallel (fork/join in the diagram).
    Tasks without a group or with unique groups run sequentially.
    Groups execute in order of first appearance within the sub-phase.

    systemDiagram must be an array of {title: str, diagram: str} objects:
    - At minimum: one class/entity diagram + one sequence diagram
    - Multiple sequence diagrams are encouraged for multi-flow features
    - Example: [{"title": "Class Diagram", "diagram": "classDiagram\n..."}, {"title": "Auth Flow", "diagram": "sequenceDiagram\n..."}]

    Scope is separate from the plan — use workspace_set_scope to define the phase-keyed scope map."""
    result = plan_service.set_plan(db, ws, plan)
    if "ok" in result:
        if ws["yolo_mode"]:
            db.execute("UPDATE workspaces SET plan_status = 'approved', scope_status = 'approved' WHERE id = ?", (ws["id"],))
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_plan(ws, project, db, locale) -> dict:
    """Get the full execution plan including system diagram and all sub-phases with tasks.

    Returns the complete plan JSON: description, systemDiagram, and execution array with
    tasks per sub-phase. Use workspace_get_state to see the current scope map."""
    return plan_service.get_plan(ws)


@mcp.tool()
@with_mcp_workspace
def workspace_extend_plan(ws, project, db, locale, subphase: dict, scope: dict, diagrams: list = None, replace_diagrams: bool = False) -> dict:
    """Append a new sub-phase to the execution plan without rewriting existing sub-phases.

    - subphase: a single execution item with 'name' (string) and 'tasks' (list of task objects).
      The 'id' is auto-assigned as 3.(max_n+1). Each task needs: title (string), files (list), agent (string).
      Optional task fields: group (string), status (string, default 'pending').
    - scope: scope entry for the new sub-phase with must and may patterns, e.g. {"must": ["src/foo/"], "may": ["src/bar/"]}
    - diagrams: optional list of system diagrams to add, each with 'title' (string) and 'diagram' (string, Mermaid syntax).
      By default, diagrams are appended to the existing list. Set replace_diagrams=true to replace the entire list.
    - replace_diagrams: if true, replace all existing diagrams with the provided list. If false (default), append.

    The plan_status and scope_status are set to 'pending' (approval revoked).
    Existing sub-phases and their data are not modified."""
    result = plan_service.extend_plan(db, ws, subphase, scope, diagrams, replace_diagrams)
    if "ok" in result:
        if ws["yolo_mode"]:
            db.execute("UPDATE workspaces SET plan_status = 'approved', scope_status = 'approved' WHERE id = ?", (ws["id"],))
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_restore_plan(ws, project, db, locale) -> dict:
    """Restore the previous plan version, swapping it with the current plan.

    Only works if current plan is NOT approved. If you need to revert an incorrectly
    set plan, call this before the user approves it.

    The previous plan's phase position is also restored — you'll return to wherever
    you were when that plan was active.
    """
    if not ws["prev_plan_json"]:
        return {"error": t("mcp.error.noPreviousPlan", locale)}

    if ws["plan_status"] == "approved":
        return {"error": t("mcp.error.planApproved", locale)}

    new_ws = plan_service.restore_plan(db, ws)
    db.commit()

    return {
        "restored": True,
        "phase": new_ws["phase"],
        "plan_status": new_ws["plan_status"],
        "message": t("mcp.restorePlan.message", locale, phase=new_ws["phase"]),
    }
