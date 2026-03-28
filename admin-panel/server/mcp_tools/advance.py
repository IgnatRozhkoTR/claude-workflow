from mcp_tools import mcp, with_mcp_workspace


@mcp.tool()
@with_mcp_workspace
def workspace_advance(ws, project, db, locale, commit_hash: str = "", no_further_research_needed: bool = False) -> dict:
    """Request phase advancement. Provide commit_hash when at commit phases (3.N.4).

    At phase 1.1 (research → proving), you MUST set no_further_research_needed=True to confirm
    you have gathered all necessary information. If you're unsure, review your research findings
    against the research discussions — post new discussions and run more research if gaps exist.

    User gates (1.4, 2.1, 3.N.3, 4.2) require human approval via admin panel — advance returns 409.
    When the user REJECTS at a gate, phase reverts to the previous step (e.g. 3.N.3 → 3.N.2).
    Read user comments via workspace_get_comments, fix the issues, then call workspace_advance
    to return to the gate for re-review. Do NOT ask the user to approve in order to fix — fix first, then re-submit."""
    from advance.orchestrator import perform_advance
    body = {}
    if commit_hash:
        body["commit_hash"] = commit_hash
    if no_further_research_needed:
        body["no_further_research_needed"] = True
    result, code = perform_advance(ws, project["path"], body)
    return result
