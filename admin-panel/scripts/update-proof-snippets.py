#!/usr/bin/env python3
"""Update proof snippets in research entries to precise 15-line quotes.

For each finding with a proof.file reference, reads the actual file,
picks the most relevant ~15 lines within the specified range,
and updates proof.line_start, proof.line_end, and proof.snippet.

Usage:
    python3 scripts/update-proof-snippets.py [--dry-run]
"""
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "server" / "admin-panel.db"
MAX_LINES = 15


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def read_file_lines(file_path: Path) -> list[str] | None:
    """Read a file and return its lines (1-indexed access via lines[line_num - 1])."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except FileNotFoundError:
        print(f"  WARNING: file not found: {file_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  WARNING: could not read {file_path}: {e}", file=sys.stderr)
        return None


def pick_best_lines(all_lines: list[str], line_start: int, line_end: int) -> tuple[int, int, str]:
    """Pick the most relevant up to MAX_LINES lines from the range [line_start, line_end].

    Line numbers are 1-indexed. Returns (new_start, new_end, snippet_text).

    Strategy:
    - If the range is <= MAX_LINES, use it as-is.
    - If the range is larger, prefer the beginning (first MAX_LINES lines),
      since class/method declarations typically appear first.
    - Clamp to actual file bounds.
    """
    total_lines = len(all_lines)

    # Clamp to valid range
    clamped_start = max(1, min(line_start, total_lines))
    clamped_end = max(clamped_start, min(line_end, total_lines))

    range_size = clamped_end - clamped_start + 1

    if range_size <= MAX_LINES:
        selected_start = clamped_start
        selected_end = clamped_end
    else:
        # Range is larger than MAX_LINES — take first MAX_LINES lines from the range
        # (covers class/method declaration and the beginning of the body)
        selected_start = clamped_start
        selected_end = clamped_start + MAX_LINES - 1

    # Extract the lines (0-indexed in list, 1-indexed for line numbers)
    selected_lines = all_lines[selected_start - 1:selected_end]
    snippet = "".join(selected_lines).rstrip("\n")

    return selected_start, selected_end, snippet


def process_finding(finding: dict, working_dir: Path, entry_id: int, finding_idx: int) -> bool:
    """Process a single finding, updating its proof snippet in-place.

    Returns True if the finding was modified.
    """
    proof = finding.get("proof")
    if not proof:
        return False

    proof_file = proof.get("file")
    if not proof_file:
        return False

    line_start = proof.get("line_start")
    line_end = proof.get("line_end")

    if line_start is None or line_end is None:
        print(f"  Finding {finding_idx}: skipping — missing line_start or line_end")
        return False

    full_path = working_dir / proof_file
    all_lines = read_file_lines(full_path)
    if all_lines is None:
        return False

    new_start, new_end, snippet = pick_best_lines(all_lines, line_start, line_end)

    old_snippet = proof.get("snippet", "")
    old_start = proof.get("line_start")
    old_end = proof.get("line_end")

    changed = (
        old_start != new_start
        or old_end != new_end
        or old_snippet != snippet
    )

    if changed:
        print(f"  Finding {finding_idx} [{proof_file}]: lines {old_start}-{old_end} -> {new_start}-{new_end}")
        proof["line_start"] = new_start
        proof["line_end"] = new_end
        proof["snippet"] = snippet
    else:
        print(f"  Finding {finding_idx} [{proof_file}]: already precise ({new_start}-{new_end}), no change")

    return changed


def main():
    dry_run = "--dry-run" in sys.argv

    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    db = get_db()
    try:
        rows = db.execute("""
            SELECT r.id, r.findings_json, w.working_dir
            FROM research_entries r
            JOIN workspaces w ON r.workspace_id = w.id
            ORDER BY r.id
        """).fetchall()

        if not rows:
            print("No research entries found.")
            return

        print(f"Found {len(rows)} research entries.\n")
        total_updated = 0

        for row in rows:
            entry_id = row["id"]
            working_dir = Path(row["working_dir"])

            try:
                findings = json.loads(row["findings_json"])
            except json.JSONDecodeError as e:
                print(f"Entry {entry_id}: ERROR parsing findings_json: {e}")
                continue

            print(f"Entry {entry_id} (working_dir: {working_dir}):")
            print(f"  {len(findings)} finding(s)")

            any_changed = False
            for i, finding in enumerate(findings):
                changed = process_finding(finding, working_dir, entry_id, i)
                if changed:
                    any_changed = True

            if any_changed:
                updated_json = json.dumps(findings, ensure_ascii=False)
                if dry_run:
                    print(f"  [DRY RUN] Would update entry {entry_id}")
                else:
                    db.execute(
                        "UPDATE research_entries SET findings_json = ? WHERE id = ?",
                        (updated_json, entry_id)
                    )
                    db.commit()
                    print(f"  Updated entry {entry_id} in DB.")
                total_updated += 1
            else:
                print(f"  No changes for entry {entry_id}.")

            print()

        print(f"Done. Updated {total_updated} entries.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
