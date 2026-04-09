Run the governed preparation workflow for this workspace only.

Hard boundaries:

- This run is phase 1 only: `1.0`, `1.1`, `1.2`, `1.3`, then stop at `1.4`.
- Do not plan. Do not implement. Do not edit repository files.
- Use the `workspace` MCP tools for all saved output and phase transitions.
- Use subagents. Do not perform deep research or proving in the parent agent.

Before doing anything else:

1. Read `AGENTS.md`.
2. Read `skills/plan-preparation/SKILL.md` for the exact phase-1 workflow expectations.
3. Read the role cards under `.codex/agents/`.
4. Call `workspace_get_state`.

Execution rules:

- If the current phase is `0`, call `workspace_advance` once to enter `1.0`.
- If the current phase is already `1.4` or beyond, stop immediately and report that phase 1 is already complete.
- For phase `1.0`, delegate assessment to the `plan-advisor` subagent.
- For phase `1.1`, create separate researcher subagents per research topic. Choose `code-researcher`, `senior-code-researcher`, `web-researcher`, or `diff-researcher` based on where the answer lives.
- Every research subagent must save findings through `workspace_save_research`, with a summary and typed proof.
- For phase `1.2`, delegate proving to `research-prover`. If proofs are rejected, rerun only the specific research topics that need correction and prove them again.
- For phase `1.3`, synthesize impact analysis from proven research, store it through `workspace_set_impact_analysis`, record progress, and advance.
- Enter `1.4` and stop. Do not proceed into planning.

Completion condition:

- Success means the workspace is at phase `1.4` and all phase-1 progress has been written through MCP.

Failure handling:

- If a required MCP operation fails, report the exact blocking error and stop.
- If you discover the workspace is already beyond the allowed phase range, stop without attempting to rewind it.
