from mcp_tools import mcp, with_mcp_workspace
from core.i18n import t
from services import discussion_service
from services import research_service


@mcp.tool()
@with_mcp_workspace
def workspace_post_discussion(ws, project, db, locale, topic: str, parent_id: int = 0, type: str = "general") -> dict:
    """Raise an open discussion point — architectural decisions, research questions, TBDs.

    These are NOT chat messages. They are important topics that need research, discussion,
    or decision from either the agent or the human. Examples:
    - 'Should we use event-driven logging or centralized logger?'
    - 'Hibernate Envers vs custom audit implementation'
    - 'Async vs sync approach for trade operation logging'

    Discussions are visible in the admin panel where either side can add context and resolve them.
    Use parent_id to reply to an existing discussion (0 = new root discussion).
    type: 'general' (default) or 'research'. Research discussions represent questions
    that need investigation — they are tracked and must have linked research findings
    before the workflow can advance past the research phase."""
    result = discussion_service.post_discussion(
        db, ws["id"], topic, author="agent",
        disc_type=type, parent_id=parent_id if parent_id else None,
    )
    if "error" in result:
        return {"error": t("mcp.error.parentDiscussionNotFound", locale, id=result.get("parent_id", ""))}
    db.commit()
    return {"ok": True, "discussion_id": result["id"]}


@mcp.tool()
@with_mcp_workspace
def workspace_save_research(ws, project, db, locale, topic: str, findings: list, discussion_id: int = 0, summary: str = "") -> dict:
    """Save research findings. Called by researcher sub-agents after investigation.

    summary: Optional 2-3 sentence human-readable overview of the overall research findings.
    If provided, it appears in research lists without requiring full findings to be loaded.

    discussion_id: Optional — ID of the research discussion this answers. Link your research
    to the discussion that raised the question. Required for advancing past research phase
    (all unresolved research discussions must have linked findings).

    Each finding must include a typed proof — a verifiable reference to actual evidence:
    {
        "summary": "What was found",
        "details": "Detailed explanation",
        "proof": { ... type-specific fields ... }
    }

    PROOF TYPES:

    type: "code" — Code reference (code-researcher, senior-code-researcher)
    {
        "type": "code",
        "file": "path/to/file.java",
        "line_start": 10,
        "line_end": 30,
        "snippet_start": 15,
        "snippet_end": 25
    }
    - file: path relative to workspace root
    - line_start/line_end: PRECISE proof range — only the lines necessary to prove your point.
      Try to stay under 20-30 lines, but no hard limit if genuinely needed.
    - snippet_start/snippet_end: a 15-line (max) window WITHIN the proof range for the
      quick-reference quote. The server reads the actual file to render this — do NOT
      send snippet text. Pick the most relevant lines from the proof range.

    type: "web" — Web source (web-researcher)
    {
        "type": "web",
        "url": "https://docs.example.com/...",
        "title": "Page Title",
        "quote": "Actual text from the source"
    }
    - url: source URL (required)
    - title: page/article title
    - quote: verbatim text from the source. Required because server cannot fetch web pages.

    type: "diff" — Git commit/diff reference (diff-researcher)
    {
        "type": "diff",
        "commit": "abc123f",
        "file": "path/to/file.java",
        "description": "What this commit shows and why it proves the finding"
    }
    - commit: commit hash (required)
    - file: specific file in the commit (optional — omit for whole-commit findings)
    - description: mandatory context explaining what the diff proves

    Returns the research entry ID for reference."""
    result = research_service.save_research(
        db, ws, topic, findings,
        discussion_id=discussion_id if discussion_id else None,
        summary=summary,
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_list_research(ws, project, db, locale) -> list:
    """List all research entries for the current workspace. Returns id, topic, findings count, and proven status.

    Does NOT return full findings content — use workspace_get_research to retrieve specific entries."""
    return research_service.list_research(db, ws["id"])


@mcp.tool()
@with_mcp_workspace
def workspace_get_research(ws, project, db, locale, ids: list) -> list:
    """Get full research entries by IDs. Use for detailed review or proving.

    Returns complete findings with proofs for each requested ID."""
    if not ids:
        return []

    return research_service.get_research(db, ws["id"], ids)


@mcp.tool()
@with_mcp_workspace
def workspace_prove_research(ws, project, db, locale, id: int, proven: bool, notes: str = "") -> dict:
    """Mark a research entry as proven or rejected. Called by prover agent after verification.

    - id: research entry ID
    - proven: True if findings verified, False if rejected
    - notes: optional explanation of verification result"""
    result = research_service.set_proven(db, id, ws["id"], proven, notes=notes)
    if "error" in result:
        return {"error": t("mcp.error.researchEntryNotFound", locale, id=id)}
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_delete_research(ws, project, db, locale, id: int) -> dict:
    """Delete a research entry. Use when findings were rejected by the prover
    and replaced by new, correct research.

    - id: research entry ID to delete"""
    deleted = research_service.delete_research(db, id, ws["id"])
    if not deleted:
        return {"error": t("mcp.error.researchEntryNotFound", locale, id=id)}
    db.commit()
    return {"ok": True, "deleted_id": id}
