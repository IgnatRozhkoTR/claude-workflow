"""Permission checking logic for tool invocations.

Evaluates whether a tool use is allowed based on workspace phase, scope,
and approval status. Called on every tool use, so performance matters.
"""
import json
import os
import re

import scope_service

_EDIT_PHASE_RE = re.compile(r'^3\.\d+\.[02]$|^4\.1$')
_COMMIT_PHASE_RE = re.compile(r'^3\.\d+\.4$|^4\.1$|^5$')

_EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

_FILE_MOD_RE = re.compile(
    r'>\s|>>\s|tee\s|dd\s.*of=|sed\s+-i|perl\s+-i|python3?\s+-c.*open\(|ruby\s+-e.*File'
    r'|\bcp\s|\bmv\s|\brm\s|\brmdir\s|\bln\s|\bchmod\s|\bchown\s|\btruncate\s|\bpatch\s'
    r'|\bfind\s.*-delete|\bfind\s.*-exec\s+rm|install\s+-'
)

_GIT_ADD_RE = re.compile(r'git\s+(-C\s+\S+\s+)?add\s')
_GIT_ADD_BROAD_RE = re.compile(r'git\s+(-C\s+\S+\s+)?add\s+(-A|--all|\.)(\s|$)')
_GIT_COMMIT_RE = re.compile(r'git\s+(-C\s+\S+\s+)?commit')
_GIT_PUSH_RE = re.compile(r'git\s+(-C\s+\S+\s+)?push')
_GIT_DESTRUCTIVE_RE = re.compile(r'git\s+(checkout\s+--|restore\s|clean\s|reset\s+--hard)')
_GH_PR_CREATE_RE = re.compile(r'gh\s+pr\s+create')
_MCP_MR_CREATE_RE = re.compile(r'mcp.*gitlab.*create_merge_request', re.IGNORECASE)
_DOCKER_RE = re.compile(r'^\s*(docker|docker-compose|podman)\s')
_CURL_APPROVE_RE = re.compile(r'curl.*(approve|reject)')
_SQLITE_BYPASS_RE = re.compile(r'sqlite3.*admin-panel|gate_nonce')
_HTTP_BYPASS_RE = re.compile(r'(curl|wget|python3?|ruby|node|fetch).*(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):5111')
_GRADLE_TEST_RE = re.compile(r'gradlew.*test')

_CLAUDE_PATH_RE = re.compile(r'(^|/)\.claude/')
_CLAUDE_PROTECTED_RE = re.compile(r'(^|/)\.claude/(worktrees|admin-panel)/')


def check_tool_permission(ws, tool_name, tool_input, project_path):
    """Route a tool invocation to the appropriate permission checker.

    Args:
        ws: workspace row (dict-like) with phase, scope_json, etc.
        tool_name: name of the tool being invoked (Edit, Bash, etc.)
        tool_input: dict with tool-specific fields (file_path, command, etc.)
        project_path: current working directory for path resolution.

    Returns:
        dict with governed, allowed, and optionally reason/updated_command.
    """
    if tool_name in _EDIT_TOOLS:
        file_path = tool_input.get("file_path", "")
        return _check_edit_tool(ws, file_path, project_path)

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return _check_bash(ws, command, project_path)

    return _check_mcp_tool(ws, tool_name)


def _requires_approval(ws):
    """Check scope and plan approval status.

    Returns:
        None if both are approved, or a denial result dict if either is not.
    """
    phase = ws["phase"]
    scope_status = ws["scope_status"] if "scope_status" in ws.keys() else "pending"
    plan_status = ws["plan_status"] if "plan_status" in ws.keys() else "pending"

    if scope_status != "approved":
        return {"governed": True, "phase": phase, "allowed": False,
                "reason": "Scope has not been approved by the user. Wait for scope approval in the admin panel."}

    if plan_status != "approved":
        return {"governed": True, "phase": phase, "allowed": False,
                "reason": "Plan has not been approved by the user. Wait for plan approval in the admin panel."}

    return None


def _is_edit_phase(phase):
    return bool(_EDIT_PHASE_RE.match(phase))


def _is_commit_phase(phase):
    return bool(_COMMIT_PHASE_RE.match(phase))


def _is_claude_metadata(file_path):
    """Check if path is a .claude/ metadata file (not worktrees or admin-panel)."""
    return (bool(_CLAUDE_PATH_RE.search(file_path))
            and not bool(_CLAUDE_PROTECTED_RE.search(file_path)))


def _canonicalize_path(file_path, cwd):
    """Make path absolute using cwd as base."""
    if not file_path:
        return file_path
    if os.path.isabs(file_path):
        return os.path.abspath(file_path)
    return os.path.abspath(os.path.join(cwd, file_path))


def _file_matches_scope(file_path, ws):
    """Check if a file path matches the workspace scope patterns."""
    ws_dir = os.path.abspath(ws["working_dir"])
    abs_file = os.path.abspath(file_path)

    if not abs_file.startswith(ws_dir + "/") and abs_file != ws_dir:
        restrict = ws["restrict_to_workspace"] if "restrict_to_workspace" in ws.keys() else 1
        if not restrict:
            return True, []
        exceptions = (ws["allowed_external_paths"] if "allowed_external_paths" in ws.keys() else "/tmp/").split(",")
        for exc in exceptions:
            exc = exc.strip()
            if exc and abs_file.startswith(exc):
                return True, []
        return False, ["(workspace directory only)"]

    scope_json = ws["scope_json"]
    if not scope_json or scope_json in ("{}", "null"):
        return True, []

    try:
        scope_map = json.loads(scope_json)
    except json.JSONDecodeError:
        return True, []

    phase = ws["phase"]
    must_patterns, may_patterns = scope_service.get_scope_patterns(scope_map, phase)
    all_patterns = must_patterns + may_patterns
    if not all_patterns:
        return True, []

    rel_path = abs_file[len(ws_dir) + 1:] if abs_file.startswith(ws_dir + "/") else file_path

    if scope_service.match_scope_patterns(rel_path, scope_map, phase):
        return True, all_patterns
    return False, all_patterns


def _extract_target_file(command):
    """Best-effort extraction of target file from a file-modifying command."""
    if re.search(r'\bcp\s|\bmv\s', command):
        parts = command.split()
        return parts[-1] if parts else ""

    if re.search(r'\brm\s', command):
        cleaned = re.sub(r'\s+-[^ ]*', '', command)
        parts = cleaned.split()
        return parts[-1] if parts else ""

    if re.search(r'\bsed\s+-i', command):
        parts = command.split()
        return parts[-1] if parts else ""

    if re.search(r'\btee\s', command):
        m = re.search(r'tee\s+(\S+)', command)
        return m.group(1) if m else ""

    if re.search(r'\bln\s', command):
        parts = command.split()
        return parts[-1] if parts else ""

    if re.search(r'\bpatch\s', command):
        parts = command.split()
        return parts[-1] if parts else ""

    if re.search(r'>>\s*|>\s*', command):
        m = re.search(r'>>?\s*(\S+)', command)
        return m.group(1) if m else ""

    return ""


def _extract_git_add_files(command):
    """Extract file paths from a git add command."""
    cleaned = re.sub(r'git\s+(-C\s+\S+\s+)?add\s+', '', command)
    return [f for f in cleaned.split() if not f.startswith("-")]


def _check_edit_tool(ws, file_path, cwd):
    """Check permission for Edit/Write/MultiEdit/NotebookEdit tools."""
    canon = _canonicalize_path(file_path, cwd)

    if _is_claude_metadata(canon):
        return {"governed": True, "phase": ws["phase"], "allowed": True,
                "reason": "Workspace metadata is always writable"}

    ws_dir = os.path.abspath(ws["working_dir"])
    if not canon.startswith(ws_dir + "/") and canon != ws_dir:
        restrict = ws["restrict_to_workspace"] if "restrict_to_workspace" in ws.keys() else 1
        if not restrict:
            return {"governed": True, "phase": ws["phase"], "allowed": True}
        exceptions = (ws["allowed_external_paths"] if "allowed_external_paths" in ws.keys() else "/tmp/").split(",")
        for exc in exceptions:
            exc = exc.strip()
            if exc and canon.startswith(exc):
                return {"governed": True, "phase": ws["phase"], "allowed": True}
        return {"governed": True, "phase": ws["phase"], "allowed": False,
                "reason": "File outside workspace directory. Modify allowed_external_paths in Configuration to add exceptions."}

    phase = ws["phase"]
    if not _is_edit_phase(phase):
        return {"governed": True, "phase": phase, "allowed": False,
                "reason": (f"File modification blocked: workspace is in phase {phase}. "
                           "Edits allowed only in phases 3.N.0 (implementation), "
                           "3.N.2 (fixes), or 4.1 (address review fixes).")}

    denial = _requires_approval(ws)
    if denial:
        return denial

    matches, patterns = _file_matches_scope(canon, ws)
    if not matches:
        return {"governed": True, "phase": phase, "allowed": False,
                "reason": (f"File outside scope: '{canon}' is not within the active scope "
                           f"for phase {phase}. Allowed: {', '.join(patterns)}")}

    return {"governed": True, "phase": phase, "allowed": True}


def _check_bash(ws, command, cwd):
    """Check permission for Bash tool commands."""
    phase = ws["phase"]
    result = {"governed": True, "phase": phase}

    if _DOCKER_RE.search(command):
        result["allowed"] = True
        return result

    if _CURL_APPROVE_RE.search(command):
        result["allowed"] = False
        result["reason"] = "Direct API calls to approve/reject are blocked. Use the admin panel UI."
        return result

    if _SQLITE_BYPASS_RE.search(command):
        result["allowed"] = False
        result["reason"] = "Direct database access to admin panel is blocked."
        return result

    if _HTTP_BYPASS_RE.search(command):
        result["allowed"] = False
        result["reason"] = "Direct HTTP requests to admin panel are blocked. Use MCP workspace tools."
        return result

    if _GIT_ADD_RE.search(command):
        return _check_git_add(ws, command, cwd)

    if _GIT_COMMIT_RE.search(command):
        if not _is_commit_phase(phase):
            result["allowed"] = False
            result["reason"] = (f"Commit blocked: workspace is in phase {phase}. "
                                "Commits allowed only in phase 3.N.4 (after code review approval).")
        else:
            result["allowed"] = True
        return result

    if _GIT_PUSH_RE.search(command):
        if phase != "5":
            result["allowed"] = False
            result["reason"] = (f"Push blocked: workspace is in phase {phase}. "
                                "Push allowed only in phase 5 (Done).")
        else:
            result["allowed"] = True
        return result

    if _GIT_DESTRUCTIVE_RE.search(command):
        if not _is_edit_phase(phase):
            result["allowed"] = False
            result["reason"] = (f"Destructive git command blocked: workspace is in phase {phase}. "
                                "Only allowed in edit phases (3.N.0, 3.N.2, 4.1).")
            return result

    if _GH_PR_CREATE_RE.search(command):
        if phase != "5":
            result["allowed"] = False
            result["reason"] = (f"PR creation blocked: workspace is in phase {phase}. "
                                "PR creation allowed only in phase 5 (Done).")
        else:
            result["allowed"] = True
        return result

    if _FILE_MOD_RE.search(command):
        return _check_file_mod_command(ws, command, cwd)

    if _GRADLE_TEST_RE.search(command) and "tee /tmp/gradle-test-output" not in command:
        state_dir = os.path.expanduser("~/.claude/state")
        updated = (
            f'set -o pipefail; ( {command} ) 2>&1 | tee /tmp/gradle-test-output.txt; '
            f'EXITCODE=${{PIPESTATUS[0]}}; '
            f'if [ "$EXITCODE" -eq 0 ]; then git diff HEAD 2>/dev/null | md5 > {state_dir}/test-pass-hash; fi; '
            f'exit $EXITCODE'
        )
        result["allowed"] = True
        result["updated_command"] = updated
        return result

    result["allowed"] = True
    return result


def _check_git_add(ws, command, cwd):
    """Check permission for git add commands."""
    phase = ws["phase"]
    result = {"governed": True, "phase": phase}

    if _GIT_ADD_BROAD_RE.search(command):
        result["allowed"] = False
        result["reason"] = ("git add -A / git add . / git add --all is blocked. "
                            "Stage specific files by name to ensure only in-scope files are committed.")
        return result

    if _is_commit_phase(phase):
        denial = _requires_approval(ws)
        if denial:
            return denial

        files = _extract_git_add_files(command)
        for staged_file in files:
            if not staged_file:
                continue
            abs_file = _canonicalize_path(staged_file, cwd)
            if _is_claude_metadata(abs_file):
                continue
            matches, patterns = _file_matches_scope(abs_file, ws)
            if not matches:
                result["allowed"] = False
                result["reason"] = (f"File outside scope: '{abs_file}' is not within the active scope "
                                    f"for phase {phase}. Allowed: {', '.join(patterns)}")
                return result

    result["allowed"] = True
    return result


def _check_file_mod_command(ws, command, cwd):
    """Check permission for file-modifying bash commands (cp, mv, sed -i, etc.)."""
    phase = ws["phase"]
    result = {"governed": True, "phase": phase}

    if not _is_edit_phase(phase):
        result["allowed"] = False
        result["reason"] = (f"File modification via Bash blocked: workspace is in phase {phase}. "
                            "File modifications only allowed in edit phases (3.N.0, 3.N.2, 4.1).")
        return result

    denial = _requires_approval(ws)
    if denial:
        return denial

    target_file = _extract_target_file(command)
    if target_file and target_file != "/dev/null":
        abs_target = _canonicalize_path(target_file, cwd)
        if not _is_claude_metadata(abs_target):
            matches, patterns = _file_matches_scope(abs_target, ws)
            if not matches:
                result["allowed"] = False
                result["reason"] = (f"File outside scope: '{abs_target}' is not within the active scope "
                                    f"for phase {phase}. Allowed: {', '.join(patterns)}")
                return result

    result["allowed"] = True
    return result


def _check_mcp_tool(ws, tool_name):
    """Check permission for MCP tool invocations."""
    phase = ws["phase"]
    result = {"governed": True, "phase": phase}

    if _MCP_MR_CREATE_RE.search(tool_name):
        if phase != "5":
            result["allowed"] = False
            result["reason"] = (f"MR creation blocked: workspace is in phase {phase}. "
                                "MR creation allowed only in phase 5 (Done).")
            return result

    result["allowed"] = True
    return result
