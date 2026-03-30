from datetime import datetime

from mcp_tools import mcp, with_mcp_workspace
from core.db import get_db
from services import verification_service


@mcp.tool()
@with_mcp_workspace
def workspace_get_verification_results(ws, project, db, locale, phase: str = "", run_id: int = 0) -> dict:
    """Get verification run results for the current workspace.

    - phase: filter by phase (e.g. "3.1.1"). Empty = latest run.
    - run_id: get specific run by ID. Takes precedence over phase.

    Returns run status and step-by-step results with output."""
    result = verification_service.get_verification_results(
        db, ws["id"], phase=phase or None, run_id=run_id if run_id else None
    )
    if not result:
        return {"message": "No verification runs found"}
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_verification_profiles(ws, project, db, locale) -> list:
    """Get all available verification profiles in the system.

    Returns profiles with their steps. Use workspace_assign_verification_profile to assign one to the current project."""
    return verification_service.get_all_profiles(db)


@mcp.tool()
@with_mcp_workspace
def workspace_create_verification_profile(ws, project, db, locale, name: str, language: str, description: str = "",
                                           lsp_command: str = "", lsp_args: str = "",
                                           lsp_install_check_command: str = "", lsp_install_command: str = "",
                                           lsp_workspace_config: str = "", lsp_port: int = 0) -> dict:
    """Create a new verification profile. Use workspace_add_verification_step to add steps after creation.

    - name: display name (e.g. "Go", "Rust", "Java (Custom)")
    - language: language key (e.g. "go", "rust", "java")
    - description: what this profile checks
    - lsp_command: LSP server binary (e.g. "jdtls", "pyright-langserver"). Required for LSP button to appear.
    - lsp_args: JSON array of CLI args (e.g. '["--stdio"]'). Optional.
    - lsp_install_check_command: command to check if LSP server is installed (e.g. "which jdtls"). Optional.
    - lsp_install_command: command to install the LSP server (e.g. "brew install jdtls"). Optional.
    - lsp_workspace_config: JSON workspace config for the LSP server. Optional.
    - lsp_port: fixed port for the LSP server (0 = auto). Optional."""
    if not name or not name.strip():
        return {"error": "Name is required"}
    if not language or not language.strip():
        return {"error": "Language is required"}
    result = verification_service.create_profile(
        db, name, language, description=description or None,
        lsp_command=lsp_command or None, lsp_args=lsp_args or None,
        lsp_install_check_command=lsp_install_check_command or None,
        lsp_install_command=lsp_install_command or None,
        lsp_workspace_config=lsp_workspace_config or None,
        lsp_port=lsp_port if lsp_port else None
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_add_verification_step(ws, project, db, locale, profile_id: int, name: str, command: str,
                                     description: str = "", install_check_command: str = "",
                                     install_command: str = "", enabled: bool = True,
                                     sort_order: int = 0, timeout: int = 120,
                                     fail_severity: str = "blocking") -> dict:
    """Add a verification step to a profile.

    - profile_id: which profile to add the step to
    - name: step name (e.g. "Compilation", "Lint")
    - command: the shell command to run
    - install_check_command: optional — checks if tool is present
    - install_command: optional — installs tool if check fails
    - enabled: whether this step runs (default true)
    - sort_order: execution order (0 = first)
    - timeout: seconds, 0 = no timeout (default 120)
    - fail_severity: 'blocking' (stops advance) or 'warning' (logged only)"""
    if fail_severity not in ("blocking", "warning"):
        return {"error": "fail_severity must be 'blocking' or 'warning'"}
    result = verification_service.add_step(
        db, profile_id, name, command,
        description=description or None,
        install_check_command=install_check_command or None,
        install_command=install_command or None,
        enabled=enabled, sort_order=sort_order, timeout=timeout, fail_severity=fail_severity
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_assign_verification_profile(ws, project, db, locale, profile_id: int, subpath: str = ".") -> dict:
    """Assign a verification profile to the current project (applies to all workspaces in the project).

    - profile_id: ID of the profile to assign (from workspace_get_verification_profiles)
    - subpath: subdirectory to run in (default "." = workspace root). Use for multi-language projects."""
    result = verification_service.assign_profile(db, ws["project_id"], profile_id, subpath=subpath)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_submit_validation(ws, project, db, locale, phase: str, status: str, findings: list = None) -> dict:
    """Submit validation results from a validator agent. Replaces file-based validation/3.N.json.

    - phase: the current phase (e.g. "3.1.1")
    - status: 'clean' (no issues) or 'dirty' (issues found)
    - findings: optional list of finding descriptions (strings)"""
    if status not in ("clean", "dirty"):
        return {"error": "Status must be 'clean' or 'dirty'"}

    now = datetime.now().isoformat()
    run_cursor = db.execute(
        "INSERT INTO verification_runs (workspace_id, phase, status, started_at, completed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws["id"], phase, "passed" if status == "clean" else "failed", now, now)
    )
    run_id = run_cursor.lastrowid

    if findings:
        for finding in findings:
            db.execute(
                "INSERT INTO verification_step_results (run_id, step_name, profile_name, status, output, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, "Code Review", "Agent Validation", "failed" if status == "dirty" else "passed",
                 finding if isinstance(finding, str) else str(finding), 0)
            )

    db.commit()
    return {"ok": True, "run_id": run_id}
