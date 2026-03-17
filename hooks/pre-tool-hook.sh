#!/bin/bash
# Phase-gated PreToolUse hook
# Reads workspace phase from SQLite DB, enforces phase restrictions

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

STATE_DIR="$HOME/.claude/state"
DB_PATH="$HOME/.claude/admin-panel/server/admin-panel.db"
mkdir -p "$STATE_DIR"

# ─── Get phase and workspace_dir from DB ───
# Returns "phase|working_dir" or empty string if no active workspace found
get_workspace_info() {
  local dir="$1"
  if [ ! -f "$DB_PATH" ]; then
    echo ""
    return
  fi

  # Try exact match on working_dir, then parent dirs
  local check_dir="$dir"
  while [ "$check_dir" != "/" ]; do
    local safe_dir
    safe_dir=$(echo "$check_dir" | sed "s/'/''/g")
    local result
    result=$(sqlite3 "$DB_PATH" "SELECT phase || '|' || working_dir FROM workspaces WHERE working_dir = '$safe_dir' AND status = 'active' LIMIT 1;" 2>/dev/null)
    if [ -n "$result" ]; then
      echo "$result"
      return
    fi
    check_dir=$(dirname "$check_dir")
  done
  echo ""
}

deny() {
  jq -n --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

# Helper: check if phase is an execution/fix phase where edits are allowed
is_edit_phase() {
  local p="$1"
  # 3.N.0 (implementation), 3.N.2 (fixes), 4.1 (address review fixes)
  echo "$p" | grep -qE '^3\.[0-9]+\.0$|^3\.[0-9]+\.2$|^4\.1$'
}

# Helper: check if phase is a commit phase
is_commit_phase() {
  local p="$1"
  # 3.N.4 (commit after review), 4.1 (address & fix), 5 (done)
  echo "$p" | grep -qE '^3\.[0-9]+\.4$|^4\.1$|^5$'
}

# Helper: check if a file path is within active scope
check_file_scope() {
  local file_path="$1"
  if [ -z "$file_path" ]; then
    return
  fi

  local ws_info
  ws_info=$(get_workspace_info "$CWD")
  if [ -z "$ws_info" ]; then
    return
  fi
  local ws_dir
  ws_dir=$(echo "$ws_info" | cut -d'|' -f2-)

  local safe_ws_dir
  safe_ws_dir=$(echo "$ws_dir" | sed "s/'/''/g")

  local ws_data
  ws_data=$(sqlite3 "$DB_PATH" "SELECT scope_json || '|' || phase FROM workspaces WHERE working_dir = '$safe_ws_dir' AND status = 'active' LIMIT 1;" 2>/dev/null)

  local scope_json phase
  scope_json=$(echo "$ws_data" | cut -d'|' -f1)
  phase=$(echo "$ws_data" | cut -d'|' -f2)

  if [ -z "$scope_json" ] || [ "$scope_json" = "{}" ] || [ "$scope_json" = "null" ]; then
    return
  fi

  local allowed
  if echo "$phase" | grep -qE '^3\.[0-9]+\.[0-9]+$'; then
    local sub_key
    sub_key=$(echo "$phase" | sed 's/\.[0-9]*$//')
    allowed=$(echo "$scope_json" | jq -r --arg key "$sub_key" '.[$key] // {} | (.must // []) + (.may // []) | .[]' 2>/dev/null)
  else
    allowed=$(echo "$scope_json" | jq -r '[.[] | (.must // []) + (.may // [])] | add // [] | .[]' 2>/dev/null)
  fi

  if [ -n "$allowed" ]; then
    local match_found=false
    # Make file_path relative to workspace dir for matching
    local rel_path="$file_path"
    if [ -n "$ws_dir" ] && [ "$file_path" != "${file_path#$ws_dir/}" ]; then
      rel_path="${file_path#$ws_dir/}"
    fi
    while IFS= read -r pattern; do
      # Convert glob pattern to regex: ** → .*, * → [^/]*, trailing / → match children
      local regex
      regex=$(echo "$pattern" | sed 's|\*\*|DBLSTAR|g; s|\*|[^/]*|g; s|DBLSTAR|.*|g; s|/$|/.*|')
      if echo "$rel_path" | grep -qE "^$regex"; then
        match_found=true
        break
      fi
    done <<< "$allowed"

    if [ "$match_found" = false ]; then
      deny "File outside scope: '$file_path' is not within the active scope for phase $phase. Allowed: $(echo "$allowed" | tr '\n' ', ')"
    fi
  fi
}

# ─── Edit/Write tools: enforce phase and scope ───
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ] || [ "$TOOL_NAME" = "MultiEdit" ] || [ "$TOOL_NAME" = "NotebookEdit" ]; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
  # Canonicalize path to prevent traversal
  if [ -n "$FILE_PATH" ] && command -v realpath >/dev/null 2>&1; then
    FILE_PATH=$(realpath -m "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
  fi

  # Always allow .claude/ folder files (workspace metadata, memory, configs)
  # BUT NOT .claude/worktrees/ (project code) or .claude/admin-panel/ (application code)
  if echo "$FILE_PATH" | grep -qE '(^|/)\.claude/' && ! echo "$FILE_PATH" | grep -qE '(^|/)\.claude/(worktrees|admin-panel)/'; then
    exit 0
  fi
  WORKSPACE_INFO=$(get_workspace_info "$CWD")
  PHASE=$(echo "$WORKSPACE_INFO" | cut -d'|' -f1)

  # If no active workspace, allow (not governed)
  if [ -z "$PHASE" ]; then
    exit 0
  fi

  # Only allow file edits in implementation/fix phases
  if ! is_edit_phase "$PHASE"; then
    deny "File modification blocked: workspace is in phase $PHASE. Edits allowed only in phases 3.N.0 (implementation), 3.N.2 (fixes), or 4.1 (address review fixes)."
  fi

  # Scope enforcement
  check_file_scope "$FILE_PATH" 

  exit 0
fi

# ─── Bash tool: intercept git commands and curl bypass ───
if [ "$TOOL_NAME" = "Bash" ]; then

  # Allow all Docker/container commands (docker rm, docker cp match file-mod patterns)
  if echo "$COMMAND" | grep -qE '^\s*(docker|docker-compose|podman)\s'; then
    exit 0
  fi

  # Block curl to approve/reject endpoints (agent bypass prevention)
  if echo "$COMMAND" | grep -qE 'curl.*(approve|reject)'; then
    deny "Direct API calls to approve/reject are blocked. Use the admin panel UI."
  fi

  # Git add — block broad staging, enforce scope on specific files
  if echo "$COMMAND" | grep -qE 'git\s+add|git\s+-C\s+\S+\s+add'; then
    WORKSPACE_INFO=$(get_workspace_info "$CWD")
    PHASE=$(echo "$WORKSPACE_INFO" | cut -d'|' -f1)
    if [ -n "$PHASE" ]; then
      # Block git add -A, git add ., git add --all (too broad)
      if echo "$COMMAND" | grep -qE 'git\s+(-C\s+\S+\s+)?add\s+(-A|--all|\.)(\s|$)'; then
        deny "git add -A / git add . / git add --all is blocked. Stage specific files by name to ensure only in-scope files are committed."
      fi

      # In commit phases, check each staged file is in scope
      if is_commit_phase "$PHASE"; then
        GIT_ADD_FILES=$(echo "$COMMAND" | sed -E 's/git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?add[[:space:]]+//' | tr ' ' '\n' | grep -v '^-')
        GIT_ADD_WS_DIR=$(echo "$WORKSPACE_INFO" | cut -d'|' -f2-)
        if [ -n "$GIT_ADD_FILES" ] && [ -n "$GIT_ADD_WS_DIR" ]; then
          while IFS= read -r staged_file; do
            [ -z "$staged_file" ] && continue
            ABS_FILE="$staged_file"
            case "$ABS_FILE" in
              /*) ;;
              *) ABS_FILE="$CWD/$ABS_FILE" ;;
            esac
            if command -v realpath >/dev/null 2>&1; then
              ABS_FILE=$(realpath -m "$ABS_FILE" 2>/dev/null || echo "$ABS_FILE")
            fi
            if echo "$ABS_FILE" | grep -qE '(^|/)\.claude/'; then
              continue
            fi
            check_file_scope "$ABS_FILE"
          done <<< "$GIT_ADD_FILES"
        fi
      fi
    fi
    exit 0
  fi

  # Git commit — only in commit phases (3.N.4)
  if echo "$COMMAND" | grep -qE 'git\s+commit|git\s+-C\s+\S+\s+commit'; then
    PHASE=$(echo "$(get_workspace_info "$CWD")" | cut -d'|' -f1)
    if [ -n "$PHASE" ] && ! is_commit_phase "$PHASE"; then
      deny "Commit blocked: workspace is in phase $PHASE. Commits allowed only in phase 3.N.4 (after code review approval)."
    fi
    exit 0
  fi

  # Git push — only at phase 5 (done)
  if echo "$COMMAND" | grep -qE 'git\s+push|git\s+-C\s+\S+\s+push'; then
    PHASE=$(echo "$(get_workspace_info "$CWD")" | cut -d'|' -f1)
    if [ -n "$PHASE" ] && [ "$PHASE" != "5" ]; then
      deny "Push blocked: workspace is in phase $PHASE. Push allowed only in phase 5 (Done)."
    fi
    exit 0
  fi

  # Git destructive commands — blocked outside edit phases (no scope check, they operate on git state)
  if echo "$COMMAND" | grep -qE 'git\s+(checkout\s+--|restore\s|clean\s|reset\s+--hard)'; then
    PHASE=$(echo "$(get_workspace_info "$CWD")" | cut -d'|' -f1)
    if [ -n "$PHASE" ] && ! is_edit_phase "$PHASE"; then
      deny "Destructive git command blocked: workspace is in phase $PHASE. Only allowed in edit phases (3.N.0, 3.N.2, 4.1)."
    fi
  fi

  # Block file-modifying commands outside edit phases + scope check in edit phases
  if echo "$COMMAND" | grep -qE '>\s|>>\s|tee\s|dd\s.*of=|sed\s+-i|perl\s+-i|python3?\s+-c.*open\(|ruby\s+-e.*File|\bcp\s|\bmv\s|\brm\s|\brmdir\s|\bln\s|\bchmod\s|\bchown\s|\btruncate\s|\bpatch\s|\bfind\s.*-delete|\bfind\s.*-exec\s+rm|install\s+-'; then
    PHASE=$(echo "$(get_workspace_info "$CWD")" | cut -d'|' -f1)
    if [ -n "$PHASE" ]; then
      if ! is_edit_phase "$PHASE"; then
        deny "File modification via Bash blocked: workspace is in phase $PHASE. File modifications only allowed in edit phases (3.N.0, 3.N.2, 4.1)."
      fi
      # In edit phases: best-effort scope check on extractable file paths
      TARGET_FILE=""
      if echo "$COMMAND" | grep -qE '\bcp\s|\bmv\s'; then
        TARGET_FILE=$(echo "$COMMAND" | awk '{print $NF}')
      elif echo "$COMMAND" | grep -qE '\brm\s'; then
        # For rm, extract the last non-flag argument
        TARGET_FILE=$(echo "$COMMAND" | sed 's/\s\+-[^ ]*//g' | awk '{print $NF}')
      elif echo "$COMMAND" | grep -qE '\bsed\s+-i'; then
        TARGET_FILE=$(echo "$COMMAND" | awk '{print $NF}')
      elif echo "$COMMAND" | grep -qE '\btee\s'; then
        TARGET_FILE=$(echo "$COMMAND" | sed -n 's/.*tee\s\+\([^ ]*\).*/\1/p')
      elif echo "$COMMAND" | grep -qE '\bln\s'; then
        TARGET_FILE=$(echo "$COMMAND" | awk '{print $NF}')
      elif echo "$COMMAND" | grep -qE '\bpatch\s'; then
        TARGET_FILE=$(echo "$COMMAND" | awk '{print $NF}')
      elif echo "$COMMAND" | grep -qE '>\s|>>\s'; then
        TARGET_FILE=$(echo "$COMMAND" | sed -n 's/.*>>\?\s*\([^ ]*\).*/\1/p')
      fi
      # Canonicalize and check scope
      if [ -n "$TARGET_FILE" ] && [ "$TARGET_FILE" != "/dev/null" ]; then
        if command -v realpath >/dev/null 2>&1; then
          TARGET_FILE=$(realpath -m "$TARGET_FILE" 2>/dev/null || echo "$TARGET_FILE")
        fi
        # Allow metadata files
        if ! echo "$TARGET_FILE" | grep -qE '(^|/)\.claude/'; then
          check_file_scope "$TARGET_FILE"
        fi
      fi
    fi
  fi

  # Block direct DB access to read nonces
  if echo "$COMMAND" | grep -qE 'sqlite3.*admin-panel|gate_nonce'; then
    deny "Direct database access to admin panel is blocked."
  fi

  # Block HTTP requests to admin panel (nonce bypass prevention)
  if echo "$COMMAND" | grep -qE '(curl|wget|python3?|ruby|node|fetch).*localhost:5111'; then
    deny "Direct HTTP requests to admin panel are blocked. Use MCP workspace tools."
  fi

  # gh pr create — only at phase 5
  if echo "$COMMAND" | grep -qE 'gh\s+pr\s+create'; then
    PHASE=$(echo "$(get_workspace_info "$CWD")" | cut -d'|' -f1)
    if [ -n "$PHASE" ] && [ "$PHASE" != "5" ]; then
      deny "PR creation blocked: workspace is in phase $PHASE. PR creation allowed only in phase 5 (Done)."
    fi
    exit 0
  fi

  # Gradle test — save output, record hash on success
  if echo "$COMMAND" | grep -qE 'gradlew.*test' && ! echo "$COMMAND" | grep -q 'tee /tmp/gradle-test-output'; then
    MODIFIED=$(printf 'set -o pipefail; ( %s ) 2>&1 | tee /tmp/gradle-test-output.txt; EXITCODE=${PIPESTATUS[0]}; if [ "$EXITCODE" -eq 0 ]; then git diff HEAD 2>/dev/null | md5 > %s/test-pass-hash; fi; exit $EXITCODE' "$COMMAND" "$STATE_DIR")
    jq -n --arg cmd "$MODIFIED" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        updatedInput: { command: $cmd },
        additionalContext: "Test output is saved to /tmp/gradle-test-output.txt. If tests fail, use Read on this file to understand the actual errors. Do not retry without reading the output first."
      }
    }'
    exit 0
  fi
fi

# ─── MCP tools: intercept GitLab MR creation ───
if echo "$TOOL_NAME" | grep -qiE 'mcp.*gitlab.*create_merge_request'; then
  PHASE=$(echo "$(get_workspace_info "$CWD")" | cut -d'|' -f1)
  if [ -n "$PHASE" ] && [ "$PHASE" != "5" ]; then
    deny "MR creation blocked: workspace is in phase $PHASE. MR creation allowed only in phase 5 (Done)."
  fi
fi

exit 0
