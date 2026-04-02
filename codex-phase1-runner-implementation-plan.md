# Codex Phase 1 Runner Implementation Plan

Date: 2026-04-01

## Goal

Add an optional Codex-based runner for phase 1 only:

- `1.0` Assessment
- `1.1` Research
- `1.2` Research proving
- `1.3` Impact analysis
- stop at `1.4` Preparation Review

Everything else stays on Claude exactly as it works today.

The feature must be:

- off by default
- silent/headless
- read-only for repo files
- web-capable
- able to use the existing workspace MCP tools
- subagent-driven, not single-agent "do everything yourself"

## Short Recommendation

This is a good feature, but the clean v1 is:

1. Store a single device-level boolean in the database: `global_flags.codex_phase1_enabled`.
2. Show a second start button on the workspace dashboard when that flag is on.
3. Launch a dedicated `codex exec` tmux session for phase 1 only.
4. Keep Codex orchestration self-contained in checked-in `.codex/` config plus a dedicated phase-1 prompt template.
5. Stop at the existing user gate at `1.4`.

The setup wizard checkbox should be the source of truth in v1, but it should stay device-scoped. It should not be copied into projects or workspaces, and it should not be wired into the setup agent prompt.

## Why This Fits The Current Repo

The current code already has the right seams:

- phase 1 is already explicitly modeled as `0 -> 1.0 -> 1.1 -> 1.2 -> 1.3 -> 1.4 -> 2.0` in `admin-panel/server/advance/phases/preparation.py`
- workspace runtime settings already live on `workspaces` in `admin-panel/server/migrations/0003_workspace_columns.py`
- the dashboard already has a start-button strip in `admin-panel/templates/admin.html`
- workspace state already feeds UI flags through `admin-panel/server/routes/state.py` and `admin-panel/templates/js/state.js`
- terminal start/resume is already isolated in `admin-panel/server/routes/terminal_routes.py`
- worktree provisioning already installs static agent config artifacts like `CLAUDE.md` and `.mcp.json` in `admin-panel/server/routes/workspaces.py`

That means this can be added as a parallel path. It does not require a full provider abstraction.

## Scope Boundary

### In scope

- one feature flag for "run phase 1 with Codex"
- one Codex phase-1 start button
- dedicated Codex phase-1 runner
- Codex project config and subagent definitions
- reuse of existing workspace MCP tools
- automatic stop at `1.4`

### Out of scope

- Codex planning
- Codex execution phases
- Codex file-edit hooks
- replacing the existing Claude start/resume flow
- Claude Code plugin bridge to Codex

The plugin bridge idea is still interesting, but it should not be the baseline for this feature.

## Product Behavior

### User-facing behavior

When the global flag is off:

- the product behaves exactly as it does now

When the global flag is on:

- the normal Claude start button still exists
- a second button appears next to it for Codex phase 1
- clicking the button launches a dedicated Codex phase-1 run in the terminal area
- Codex advances through `1.0` to `1.4`
- Codex stops once preparation is complete and the workspace is awaiting user review at `1.4`
- planning from `2.0` onward still uses Claude

### Phase behavior

The Codex runner should:

1. read current workspace state through MCP
2. if needed, advance from `0` to `1.0`
3. run assessment via a dedicated plan-advisor subagent
4. fan out research into separate subagents
5. prove research via dedicated prover subagent work
6. perform impact analysis and progress updates
7. enter the `1.4` gate and stop

It should not continue into `2.0` planning.

## Storage Model

### Recommended v1

Add a small device-scoped table:

- `global_flags(flag_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)`

Store one row for:

- `codex_phase1_enabled`

Why device-level is the right model:

- your clarified UX is machine-wide, not project-specific and not workspace-specific
- the setup wizard already behaves like a machine-level configuration surface
- the flag only controls feature exposure, not per-workspace persisted behavior

Do not send this value inside the existing `/api/setup/start` payload. That route still exists only to drive the Claude setup agent.

## UI Plan

### 1. Setup wizard toggle

Add a single checkbox in the setup wizard:

- label: `Use Codex For Phase 1`
- default: unchecked
- saves to the global device-level flag in the database

This should not be included in the setup-agent payload builder.

### 2. Dashboard launch button

The existing start strip in `admin-panel/templates/admin.html` already has:

- Claude label
- Start
- Sessions
- Path

Add a second launch group when the global flag is true:

- label: `Codex`
- button: `Start Phase 1`

Show it only when the workspace phase is before the completion of phase 1. Recommended visibility:

- visible for `0`, `1.0`, `1.1`, `1.2`, `1.3`
- hidden or disabled at `1.4` and above

### 3. Setup wizard integration

Persist it via a separate API call, keep it out of `getSetupConfig()`, and keep it out of `/api/setup/start`.

## Backend Plan

### 1. Schema and state

Add a device-scoped flags table via a migration and expose the relevant flag through:

- `admin-panel/server/routes/setup.py`
- `admin-panel/server/routes/state.py`
- `admin-panel/templates/js/state.js`

Also add small setup-scoped feature routes:

- `GET /api/setup/features`
- `PUT /api/setup/features`

Payload shape:

- `{ "codex_phase1_enabled": true|false }`

### 2. Dedicated terminal route

Do not overload the existing Claude start route.

Add a separate endpoint:

- `POST /api/ws/<project>/<branch>/terminal/codex-phase1/start`

Optional later:

- `POST /api/ws/<project>/<branch>/terminal/codex-phase1/kill`
- `GET /api/ws/<project>/<branch>/terminal/codex-phase1/status`

This keeps the Claude routes unchanged and makes the feature easy to remove if needed.

### 3. Separate tmux session name

The current terminal layer assumes one tmux session per workspace:

- `session_name(project_id, branch)` -> `ws-...`

That is not enough for a second runner. If reused directly, Codex phase 1 would kill or replace the normal Claude session.

Recommended change:

- generalize session naming to accept a session kind
- keep existing Claude names stable
- add a dedicated kind for Codex phase 1

Example shape:

- Claude: `ws-<project>-<branch>`
- Codex phase 1: `ws-<project>-<branch>-codex-p1`

### 4. Browser terminal attachment

The current WebSocket attach path also assumes a single session per workspace.

Recommended change:

- extend the terminal attach logic to accept a session kind
- or add a dedicated Codex-phase1 attach path

Frontend should attach the terminal viewer to the Codex tmux session when the Codex phase-1 button is used.

## Codex Launch Design

### Use `codex exec`, not the interactive TUI

For this feature, the right execution mode is the non-interactive CLI:

- `codex exec`

Reasons:

- headless/silent behavior matches the requirement
- no Claude-style readiness detection is needed
- no prompt-box scraping is needed
- the run can be treated as a bounded one-shot phase runner

### Do not use `--full-auto`

Local `codex exec --help` says:

- `--full-auto` implies `--sandbox workspace-write`

That is the wrong sandbox for this feature.

Use explicit flags instead:

- `--sandbox read-only`
- `--ask-for-approval never`
- `--search`

### Recommended launch wrapper

Do not construct a giant shell string inside the route handler.

Add a small runner module or script that:

1. resolves the workspace
2. renders the phase-1 prompt template
3. launches `codex exec` with the right flags
4. streams output to the tmux pane
5. exits when the run finishes

That keeps `terminal_routes.py` small and avoids shell quoting problems.

Suggested shape:

- `admin-panel/server/core/codex_phase1.py`
- or `admin-panel/server/scripts/run_codex_phase1.py`

## Codex Repo Assets

This feature needs a real Codex project layer in the repo.

### 1. Root `AGENTS.md`

Add a repo-level `AGENTS.md` that states:

- Codex phase-1 runs are read-only
- the parent agent is an orchestrator, not the researcher/prover itself
- assessment must use the plan-advisor subagent
- research must fan out into separate researcher subagents
- proving must be delegated to dedicated prover subagent work
- all persisted output goes through workspace MCP tools
- stop at `1.4`

### 2. `.codex/config.toml`

Add project-scoped Codex config for:

- MCP server definitions
- project docs
- phase-1 profile defaults
- any subagent or behavior limits needed for fan-out

This repo already provisions `.mcp.json` for Claude. Codex needs equivalent MCP wiring in `.codex/config.toml`.

### 3. `.codex/agents/*.toml`

Add Codex-native agent definitions for the roles phase 1 needs:

- `plan-advisor`
- `code-researcher`
- `senior-code-researcher`
- `web-researcher`
- `diff-researcher`
- `research-prover`

These should be based on the existing `.claude/agents/*.md` role split, but rewritten for Codex-native agent definitions.

### 4. Dedicated phase-1 prompt template

Add one checked-in prompt template for the parent Codex runner.

This prompt should:

- start with `workspace_get_state`
- enforce phase-1-only behavior
- require subagent fan-out
- tell the parent not to do deep research itself
- require progress updates and `workspace_advance`
- require a hard stop at `1.4`

Keep this as a checked-in repo file, not an inline string buried in Python.

## Workspace Provisioning Plan

Current workspace creation already provisions:

- `.claude/settings.json`
- `CLAUDE.md`
- `.mcp.json`

For Codex phase 1, extend provisioning to include static Codex config artifacts:

- `.codex/config.toml`
- `.codex/agents/`
- optionally `AGENTS.md` if repo-local and not already present

For worktrees:

- symlink or copy the repo-level `.codex/` directory into the worktree, the same way static config artifacts are already handled

For non-worktree mode:

- treat `.codex/` as another backed-up/restored project config artifact if the project root is being mutated in place

Important:

- keep `.codex/` static
- do not rely on `.codex/` as mutable runtime state

## Orchestration Rules

### Required parent-agent behavior

The parent Codex run is an orchestrator only. It should:

- manage phase transitions
- decide which subagents to spawn
- review returned findings
- call MCP tools for phase progress and advancement

It should not personally perform the deep research tasks that were meant to be delegated.

### Required subagent behavior

For v1, the Codex instructions must explicitly require:

- one plan-advisor subagent for assessment
- one researcher subagent per research topic
- proving delegated to dedicated prover subagent work

There are two possible verifier models:

1. one prover agent for all entries
2. one prover agent per research entry

Your requested model is the stricter second one. It is possible, but it is more orchestration code than the current Claude phase-1 skill, which uses a single prover pass.

Recommendation:

- keep the requirement "proving is delegated, never done by the parent"
- decide during implementation whether verifier fan-out is worth the extra complexity in v1

If you want exact parity with your request, implement per-entry prover fan-out.

## MCP Reuse

This feature should reuse the existing workspace MCP server. That is the main reason the feature is practical.

Phase 1 already has the tools needed:

- `workspace_get_state`
- `workspace_post_discussion`
- `workspace_save_research`
- `workspace_list_research`
- `workspace_get_research`
- `workspace_prove_research`
- `workspace_set_impact_analysis`
- `workspace_update_progress`
- `workspace_advance`
- acceptance-criteria tools if you want parity with the current phase-1 flow

No new phase-1 MCP tools should be required for v1.

## Test Plan

### Backend tests

Add tests for:

- migration default is off
- setup features endpoint exposes `codex_phase1_enabled`
- setup toggle endpoint updates the global flag
- workspace state exposes the global flag so the button can be rendered correctly
- Codex phase-1 start route rejects unknown workspaces
- Codex phase-1 start route rejects when feature flag is off
- Codex phase-1 start route uses a separate tmux session name
- Claude session is not killed when Codex phase-1 session starts

### Frontend tests or smoke checks

Verify:

- checkbox defaults off
- checkbox persists after refresh
- Codex start button only appears when enabled
- Codex start button hides or disables after phase 1 is complete
- terminal attaches to the Codex tmux session, not the Claude one

### End-to-end dry run

Run one manual phase-1 pass on a disposable workspace and verify:

1. Codex starts from the button
2. it uses subagents
3. research entries are saved through MCP
4. research is proven
5. impact analysis is stored
6. progress entries are stored
7. the workspace stops at `1.4`
8. Claude start/resume still works unchanged afterward

## Recommended Delivery Order

1. Add DB column and state/toggle API.
2. Add dashboard checkbox and conditional button.
3. Generalize tmux session naming for multiple session kinds.
4. Add the Codex phase-1 start route.
5. Add repo `.codex/` assets and the phase-1 prompt template.
6. Add the runner script/module that launches `codex exec`.
7. Extend workspace provisioning for `.codex/`.
8. Run a manual dry run on a test workspace.
9. Add or finish automated tests.

## Main Risks

### 1. The flag should stay device-scoped even though the button lives in a workspace

The setup page is the right home for the toggle only because the toggle is machine-wide. Do not let it drift into project-level or workspace-level state later unless the product intent actually changes.

### 2. One-session assumption in terminal code

This is the biggest code-level trap. The current terminal stack is built around one session per workspace.

### 3. Codex prompt quality matters more than hooks

For this feature, safety comes from:

- read-only sandbox
- bounded phase scope
- strong prompt rules
- MCP-backed phase guards

not from Claude-style tool hooks.

### 4. "Read-only" and "read anything on the host" are not exactly the same requirement

If phase 1 only needs the workspace repo, web search, and MCP tools, `read-only` is the right target.

If you later decide Codex must freely inspect arbitrary host paths outside the workspace, do a separate proof-of-concept before broadening sandbox access.

## Final Recommendation

Build this as a narrow, additive path:

- one setup-wizard checkbox
- one Codex phase-1 start button
- one dedicated Codex phase-1 tmux session
- one checked-in Codex instruction layer

Do not start with:

- setup-wizard-only state
- provider abstraction
- hook parity work
- plugin bridge experiments

That keeps the feature small, reversible, and aligned with how this repo is already structured.
