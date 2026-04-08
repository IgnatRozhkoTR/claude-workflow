Run the governed phase-4 review workflow for this workspace only.

Hard boundaries:

- This run is review only and must stay within phase `4.0`.
- Do not plan. Do not implement. Do not edit repository files.
- Use the `workspace` MCP tools for all persisted findings.
- Use subagents. Do not perform the full review directly in the parent agent.

Before doing anything else:

1. Read `AGENTS.md`.
2. Read `skills/governed-workflow/SKILL.md`, especially phase `4.0`.
3. Read the review role cards under `.codex/agents/`.
4. Call `workspace_get_state`.

Execution rules:

- If the current phase is not `4.0`, stop immediately and report that Codex review only runs during phase `4.0`.
- Deploy exactly 3 reviewer subagents in parallel:
  - `clean-code-reviewer`
  - `architecture-reviewer`
  - `reliability-reviewer`
- Keep the parent agent thin. The parent coordinates, gathers results, and stops when all 3 reviewers are done.
- Do not brief reviewers with implementation history or rationale. Give them only the task description, branch, and the fact that they are performing a blind review.
- Each reviewer submits only critical or major issues through `workspace_submit_review_issue(..., reviewer_name="codex")`.
- If a reviewer finds no critical or major issue, it reports that back to the parent and submits nothing.
- Do not call `workspace_update_progress`.
- Do not call `workspace_advance`.

Completion condition:

- Success means all 3 reviewer subagents completed and any Codex findings were submitted through MCP.
- When finished, stop and let the wrapper mark the Codex review run complete.

Failure handling:

- If a required MCP operation fails, report the exact blocking error and stop.
- If the workspace is outside phase `4.0`, stop without attempting to change phase state.
