from pathlib import Path

from mcp_tools import mcp, with_mcp_workspace
from core.i18n import t
from services import comment_service


@mcp.tool()
@with_mcp_workspace
def workspace_get_comments(ws, project, db, locale, scope: str = "", unresolved_only: bool = True) -> list:
    """Get review comments, optionally filtered by scope. Returns list of comment objects (empty list if none)."""
    return comment_service.get_comments(
        db, ws["id"], scope=scope or None, unresolved_only=unresolved_only
    )


@mcp.tool()
@with_mcp_workspace
def workspace_post_comment(
    ws, project, db, locale,
    file_path: str,
    line_start: int,
    line_end: int,
    text: str,
    parent_id: int = 0,
) -> dict:
    """Post a review comment on specific file lines. Used by code-reviewer agents during review phases.

    - file_path: path relative to workspace root
    - line_start/line_end: line range being commented on
    - text: the review comment
    - parent_id: reply to existing comment (0 = new root comment)"""
    if not file_path or not file_path.strip():
        return {"error": t("mcp.error.filePathRequired", locale)}
    if not text or not text.strip():
        return {"error": t("mcp.error.textRequired", locale)}

    if parent_id > 0:
        parent = db.execute(
            "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
            (parent_id, ws["id"])
        ).fetchone()
        if not parent:
            return {"error": t("mcp.error.parentCommentNotFound", locale, id=parent_id)}

    result = comment_service.post_comment(
        db, ws["id"], text=text.strip(), scope="review", author="agent",
        target=file_path.strip(), file_path=file_path.strip(),
        line_start=line_start, line_end=line_end,
        parent_id=parent_id if parent_id > 0 else None,
    )
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_resolve_comment(ws, project, db, locale, comment_id: int) -> dict:
    """Mark a review comment as resolved. Call after addressing feedback from code review.

    - comment_id: the ID of the comment (from workspace_get_comments or workspace_get_state)
    - Only resolves comments belonging to the current workspace (security check)
    - Cannot resolve scope='review' items — use workspace_resolve_review_issue instead"""
    result = comment_service.resolve_comment(db, comment_id, ws["id"], block_review_scope=True, locale=locale)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_submit_review_issue(ws, project, db, locale, file_path: str, line_start: int, line_end: int, severity: str, description: str, reviewer_name: str = "reviewer") -> dict:
    """Submit a code review finding. Only critical and major issues are saved — minor/style issues are dropped.

    - file_path: path relative to workspace root
    - line_start: first line of the problematic code
    - line_end: last line of the problematic code
    - severity: 'critical' or 'major' (others rejected)
    - description: what the issue is and why it matters
    - reviewer_name: 'reviewer' (default) or 'codex' for Codex-authored findings"""
    if severity not in ("critical", "major"):
        return {"error": t("mcp.error.invalidSeverity", locale)}
    if reviewer_name not in ("reviewer", "codex"):
        return {"error": t("mcp.error.invalidReviewerName", locale)}

    working_dir = ws["working_dir"]
    full_path = Path(working_dir) / file_path
    if not full_path.exists():
        return {"error": t("mcp.error.fileNotFound", locale, file_path=file_path)}

    try:
        lines = full_path.read_text().splitlines()
        start = max(0, line_start - 1)
        if start >= len(lines):
            return {"error": t("mcp.error.lineStartBeyondFile", locale, line_start=line_start, length=len(lines))}
    except Exception as e:
        return {"error": t("mcp.error.failedToReadFile", locale, error=str(e))}

    result = comment_service.submit_review_issue(
        db, ws["id"], file_path, line_start, line_end, description, author=reviewer_name
    )
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_review_issues(ws, project, db, locale, status: str = "") -> list:
    """Get all review items for the current workspace.

    - status: filter by resolution ('open', 'fixed', 'false_positive', 'out_of_scope'). Empty = all.
    Returns list of review items with id, file_path, lines, description, resolution, author, resolved."""
    return comment_service.get_review_issues(
        db, ws["id"], resolution=status or None
    )


@mcp.tool()
@with_mcp_workspace
def workspace_resolve_review_issue(ws, project, db, locale, issue_id: int, resolution: str) -> dict:
    """Set the resolution on a review item. Called by agents after addressing feedback.

    - issue_id: the review item ID (from workspace_get_review_issues or workspace_get_comments)
    - resolution:
      - 'fixed': code was changed to address the issue
      - 'false_positive': issue is invalid, code is correct as-is
      - 'out_of_scope': legitimate issue but outside the allowed scope
      - 'open': reset — used by review-validator to reopen incorrectly resolved issues"""
    if resolution not in ("fixed", "false_positive", "out_of_scope", "open"):
        return {"error": t("mcp.error.invalidResolution", locale)}

    result = comment_service.resolve_review_issue(
        db, issue_id, ws["id"], resolution, locale=locale
    )
    if "ok" in result:
        db.commit()
    return result
