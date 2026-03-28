"""Research domain logic: save, list, get, prove, and delete research entries.

All research business logic lives here. MCP tools and route handlers are thin
wrappers that delegate to this module.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from core.i18n import t

logger = logging.getLogger(__name__)


def _normalize_proof_paths(findings, working_dir):
    """Resolve relative proof file paths against cwd, then make relative to working_dir."""
    cwd = os.getcwd()
    for finding in findings:
        proof = finding.get("proof", {})
        file_ref = proof.get("file")
        if not file_ref:
            continue
        abs_path = Path(cwd) / file_ref if not Path(file_ref).is_absolute() else Path(file_ref)
        abs_path = abs_path.resolve()
        try:
            proof["file"] = str(abs_path.relative_to(Path(working_dir).resolve()))
        except ValueError:
            proof["file"] = str(abs_path)


def _enrich_code_snippets(findings, working_dir):
    """Read actual file content to populate snippet text for code proofs."""
    for finding in findings:
        proof = finding.get("proof", {})
        if proof.get("type") != "code":
            continue
        if not proof.get("snippet_start") or not proof.get("snippet_end"):
            continue
        file_path = Path(working_dir) / proof["file"]
        if not file_path.exists():
            continue
        try:
            lines = file_path.read_text().splitlines()
            start = max(0, proof["snippet_start"] - 1)
            end = min(len(lines), proof["snippet_end"])
            proof["snippet"] = "\n".join(lines[start:end])
        except Exception:
            logger.warning("Failed to read proof snippet from %s", proof.get("file"), exc_info=True)


def save_research(db, ws, topic, findings, discussion_id=None, summary=""):
    """Save research findings with proof enrichment.

    Normalizes proof file paths and enriches code proofs with snippet text
    before persisting.

    Returns a result dict with ok/research_id or error key.
    """
    if not findings:
        locale = ws["locale"] or "en"
        return {"error": t("mcp.error.noFindings", locale)}

    working_dir = ws["working_dir"]
    _normalize_proof_paths(findings, working_dir)
    _enrich_code_snippets(findings, working_dir)

    resolved_discussion_id = discussion_id if discussion_id else None
    resolved_summary = summary.strip() if summary and summary.strip() else None

    cursor = db.execute(
        "INSERT INTO research_entries (workspace_id, topic, summary, findings_json, discussion_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ws["id"], topic, resolved_summary, json.dumps(findings), resolved_discussion_id, datetime.now().isoformat())
    )
    return {"ok": True, "research_id": cursor.lastrowid}


def list_research(db, workspace_id):
    """List all research entries for a workspace. Returns compact summaries without full findings."""
    rows = db.execute(
        "SELECT id, topic, summary, findings_json, proven, created_at "
        "FROM research_entries WHERE workspace_id = ? ORDER BY id",
        (workspace_id,)
    ).fetchall()
    return [
        {
            "id": row["id"],
            "topic": row["topic"],
            "summary": row["summary"],
            "findings_count": len(json.loads(row["findings_json"])),
            "proven": row["proven"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_research(db, workspace_id, ids):
    """Get full research entries by IDs including findings and proofs."""
    if not ids:
        return []

    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT id, topic, summary, findings_json, proven, proven_notes, discussion_id, created_at "
        f"FROM research_entries WHERE workspace_id = ? AND id IN ({placeholders}) ORDER BY id",
        [workspace_id] + list(ids)
    ).fetchall()
    return [
        {
            "id": row["id"],
            "topic": row["topic"],
            "summary": row["summary"],
            "findings": json.loads(row["findings_json"]),
            "proven": row["proven"],
            "proven_notes": row["proven_notes"],
            "discussion_id": row["discussion_id"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def set_proven(db, research_id, workspace_id, proven, notes=""):
    """Mark a research entry as proven or rejected.

    Returns a result dict with ok/error key.
    """
    row = db.execute(
        "SELECT id FROM research_entries WHERE id = ? AND workspace_id = ?",
        (research_id, workspace_id)
    ).fetchone()
    if not row:
        return {"error": "Research entry not found"}

    proven_val = 1 if proven else -1
    db.execute(
        "UPDATE research_entries SET proven = ?, proven_notes = ? WHERE id = ?",
        (proven_val, notes or None, research_id)
    )
    return {"ok": True, "id": research_id, "proven": proven}


def delete_research(db, research_id, workspace_id):
    """Delete a research entry. Returns True if deleted, False if not found."""
    rows = db.execute(
        "DELETE FROM research_entries WHERE id = ? AND workspace_id = ?",
        (research_id, workspace_id)
    ).rowcount
    return rows > 0
