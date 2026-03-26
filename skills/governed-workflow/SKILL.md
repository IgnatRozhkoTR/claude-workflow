---
name: governed-workflow
description: Orchestrates a governed multi-phase implementation workflow — assessment, research, planning, execution, review, and delivery — with backend-enforced phase gates, scope locking, and proof-driven research.
---

# Governed Workflow Skill

Multi-phase implementation workflow with backend-enforced transitions. Every phase advance is validated server-side — the orchestrator cannot self-certify readiness.

**Start every session by calling `workspace_get_state`.** The `phase` field tells you where you are. The `previous_sessions` field tells you whether this is a fresh start or a continuation.

---

## Agent Roles: Persistent Teammate vs Resumable Sub-agents

There are two distinct agent patterns. Only plan-advisor is a persistent teammate; all others are resumable sub-agents.

### Persistent teammate (plan-advisor only)

Created via `TeamCreate` at session start, then spawned with the `team_name` parameter:

```
TeamCreate(team_name: "<branch-name>")

Agent(
  name: "plan-advisor",
  team_name: "<branch-name>",
  subagent_type: "plan-advisor",
  ...
)
```

This makes it a real persistent teammate:
- Visible in the UI teammate list
- Stays alive between turns (goes idle, never terminates)
- Can reach out to the orchestrator proactively
- Has an inspectable chat history
- Always reachable via `SendMessage(to: "plan-advisor", ...)`

### Resumable sub-agents (all other roles)

Spawned with `Agent(name: "<role>", subagent_type: "<type>", ...)` — NO `team_name` parameter:

```
Agent(
  name: "researcher-auth",
  subagent_type: "code-researcher",
  ...
)
```

They execute their task and return. They are NOT persistent — they complete, go dormant, and wake up only when messaged. The orchestrator can continue them for follow-up via `SendMessage(to: "<name>")`.

### Spawn rules per role

| Role | Pattern | When |
|------|---------|------|
| **plan-advisor** | **Persistent teammate** (always) | Phase 0, messaged in phases 1, 3, 3.N.0 |
| senior-backend-engineer | Resumable sub-agent | Complex sub-phases spanning 3.N.0 → 3.N.2 fix cycles. Continue via SendMessage. Production code ONLY — never tests. |
| senior-backend-test-engineer | Resumable sub-agent | Complex test scenarios spanning write + fix cycles. Continue via SendMessage. Tests ONLY — always deployed AFTER engineer completes. |
| senior-code-validator | Resumable sub-agent | Continue via SendMessage when re-validation after fixes is expected |
| senior-code-researcher | Resumable sub-agent | Deep research spanning multiple rounds. Continue via SendMessage. |
| researcher (middle) | Resumable sub-agent | Phase 2.0 (parallel, one per topic) |
| research-prover | Resumable sub-agent | Phase 2.1 |
| engineer (middle) | Resumable sub-agent | Phases 3.N.0 (stage 1), 3.N.2, 3.N.4, 4.1. Production code ONLY — never tests. |
| test engineer (middle) | Resumable sub-agent | Phase 3.N.0 (stage 2, after engineer). Tests ONLY. |
| validator (middle) | Resumable sub-agent | Phase 3.N.1 |
| reviewer | Resumable sub-agent | Phase 4.0 |

**The plan-advisor is ALWAYS a persistent teammate — NEVER a sub-agent.** It is created with `TeamCreate` + `Agent(team_name: ...)` once in Phase 0 and messaged via `SendMessage(to: "plan-advisor", ...)` in every subsequent phase that needs it.

**All other agents are resumable sub-agents.** They run their task and return. For multi-phase work (e.g., senior engineer across 3.N.0 → 3.N.2 fix cycles), reuse the same agent by sending follow-up messages via `SendMessage(to: "<name>")`. They are not teammates — they do not appear in the UI teammate list and cannot proactively reach out.

---

## Phase Map

```
0         Init — spawn team
1         Assessment (plan-advisor teammate)
2.0       Research (researcher sub-agents, parallel)
2.1       Research Proving (prover sub-agent)
3.0       Planning (orchestrator + plan-advisor teammate)
3.1       Plan Review                          USER GATE
3.N.0     Implementation                       code edits ON (in scope)
3.N.1     Validation                           code edits OFF
3.N.2     Fixes (skipped if clean)             code edits ON (in scope)
3.N.3     Code Review                          USER GATE
3.N.4     Commit
4.0       Final Review                         code edits OFF
4.1       Address & Fix                        code edits ON, commits ON
4.2       Final Approval                       USER GATE
5         Done                                 push + MR allowed
```

Phases stored as strings: `"0"`, `"2.1"`, `"3.2.3"`. N = 1, 2, 3... from the approved plan.

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `workspace_get_state` | Full state: phase, scope, plan, context, research, discussions, comments, previous_sessions |
| `workspace_advance` | Request phase advancement (optional: commit_hash) |
| `workspace_set_scope` | Write scope (must/may) — planning phase only |
| `workspace_set_plan` | Write execution plan — planning phase only |
| `workspace_post_discussion` | Raise an open discussion point (architectural decisions, research questions) |
| `workspace_get_comments` | Read review comments (optionally filtered by scope) |
| `workspace_save_research` | Save research findings — called by researcher sub-agents |
| `workspace_list_research` | List all research entries (id, topic, count, proven status) |
| `workspace_get_research` | Get full research entries by IDs (findings + proofs) |
| `workspace_prove_research` | Mark a research entry proven or rejected — called by prover |
| `workspace_update_progress` | Document phase completion (required before certain advances) |
| `workspace_propose_criteria` | Propose acceptance criteria (unit_test, integration_test, bdd_scenario, custom) |
| `workspace_update_criteria` | Update criteria description or details |
| `workspace_get_criteria` | Get all acceptance criteria with their statuses |
| `workspace_extend_plan` | Append a new sub-phase to the plan without rewriting existing ones (auto-assigns ID, optional scope) |
| `workspace_submit_review_issue` | Submit a review finding with file/line location (critical/major only) |
| `workspace_get_review_issues` | Get all review items, optionally filtered by resolution status |
| `workspace_resolve_review_issue` | Set resolution on a review item (fixed, false_positive, out_of_scope) |

---

## Session Start / Recovery

**Every session — fresh or resumed — starts here:**

1. Call `workspace_get_state`
2. Read `phase` and `previous_sessions`

**Fresh start** (`phase == "0"` and `previous_sessions` is empty): proceed to Phase 0.

**Recovery** (`phase > "0"` or `previous_sessions` is non-empty): the previous session ended (compaction, restart, or manual resume). **The plan-advisor teammate from the previous session is gone — you MUST re-create it.**

1. Read `progress` entries to reconstruct what happened
2. **IMMEDIATELY re-create the plan-advisor persistent teammate** (phase >= 1):
   ```
   TeamCreate(team_name: "<branch-name>")

   Agent(
     name: "plan-advisor",
     team_name: "<branch-name>",
     subagent_type: "plan-advisor",
     prompt: "You are the plan-advisor teammate in this governed workflow session.
              Workspace: {working_dir}
              Wait for instructions from the orchestrator."
   )
   ```
3. Continue from the current phase — message the plan-advisor via `SendMessage(to: "plan-advisor", ...)`

---

## Phase 0: Init — Create Team and Spawn Plan-Advisor

**Actors**: Orchestrator

The workspace already exists (created via admin panel). This phase creates the persistent team and spawns the plan-advisor as a real teammate.

### Steps

1. Create the team and spawn `plan-advisor` as a **persistent teammate**:

```
TeamCreate(team_name: "<branch-name>")

Agent(
  name: "plan-advisor",
  team_name: "<branch-name>",
  subagent_type: "plan-advisor",
  prompt: "You are the plan-advisor teammate in this governed workflow session.
           Read and follow: ~/.claude-assistant/agents/plan-advisor.md
           Workspace: {working_dir}
           Your role: assess the codebase, advise on planning, review the execution plan.
           Wait for instructions from the orchestrator."
)
```

2. Call `workspace_advance` to move to phase 1.

**The plan-advisor is a persistent teammate — it stays alive between turns, visible in the UI teammate list, and always reachable via `SendMessage(to: "plan-advisor", ...)`.**

---

## Phase 1: Assessment

**Actor**: plan-advisor **persistent teammate** (messaged — NOT a new sub-agent)

If the plan-advisor is not yet created (skipped Phase 0 or session recovery), create the team and spawn it first (see Phase 0 steps).

Message the plan-advisor teammate:

```
SendMessage(
  to: "plan-advisor",
  content: "Begin assessment. Read workspace_get_state for context (ticket, working_dir, context notes).
            Identify affected areas of the codebase. Raise any open questions via workspace_post_discussion.
            Report your findings in a structured summary."
)
```

When assessment is complete:
1. Propose acceptance criteria via `workspace_propose_criteria` (unit tests, integration tests, BDD scenarios, custom checks). Users accept or reject them in the admin panel.
2. Call `workspace_update_progress` for phase `"1"` with a non-empty summary
3. Call `workspace_advance`

**Advance 1 → 2.0** requires: progress entry `"1"` with non-empty summary.

---

## Phase 2.0: Research

**Actors**: Researcher sub-agents (parallel, one-shot)

Deploy parallel researcher sub-agents — one per investigation topic identified in assessment. Each sub-agent:
- Investigates its topic
- Calls `workspace_save_research` with findings + typed proofs
- Each finding must include a `proof` with a `type` field. The proof format depends on the researcher type:

**type: "code"** (code-researcher, senior-code-researcher)
  - `file` — path relative to workspace root
  - `line_start`, `line_end` — PRECISE proof range. Try to stay under 20-30 lines, no hard limit.
  - `snippet_start`, `snippet_end` — 15-line max window WITHIN the proof range for the quick-reference quote
  - Do NOT include snippet text — the server reads the actual file to render quotes

**type: "web"** (web-researcher)
  - `url` — source URL (required)
  - `title` — page/article title
  - `quote` — verbatim text from the source (required — server cannot fetch web pages)

**type: "diff"** (diff-researcher)
  - `commit` — commit hash (required)
  - `file` — specific file in the commit (optional)
  - `description` — mandatory context explaining what the diff proves

Call `workspace_advance` when all researchers complete.

**Advance 2.0 → 2.1** requires: at least 1 research entry saved, all entries valid.

---

## Phase 2.1: Research Proving

**Actor**: Prover sub-agent (Opus, one-shot)

Deploy one prover sub-agent:

```
Agent(
  subagent_type: "research-prover",
  prompt: "Verify all research entries for this workspace. Mark each as proven or rejected.
           Workspace: {working_dir}"
)
```

The prover ONLY verifies — it does NOT research. It calls `workspace_prove_research` for each entry DIRECTLY — the orchestrator does NOT need to call it. Wait for the prover to finish, then check results.

If any research is rejected: re-deploy the original researcher sub-agents for those topics (to fix their proofs), then re-deploy the prover.

When all research is proven (prover confirms):
1. Call `workspace_update_progress` for phase `"2"`
2. Call `workspace_advance`

**Advance 2.1 → 3.0** requires: all research entries proven + progress entry `"2"`.

---

## Phase 3.0: Planning

**Actors**: Orchestrator + plan-advisor teammate

Message the plan-advisor teammate to collaborate on the execution plan:

```
SendMessage(
  to: "plan-advisor",
  content: "We are in the planning phase. Review the research findings via workspace_get_state.
            Help me design the execution plan. Consider whether this task needs multiple
            sub-phases or a single one. Each sub-phase needs: id (3.1, 3.2, ...),
            name, scope (must/may globs), and tasks."
)
```

**Sub-phase count guidance**: Multiple sub-phases are NOT required. Use them only when the task naturally splits into independent, separately reviewable chunks — different layers, modules, or concerns that benefit from isolated review. For simple or atomic tasks, use a single sub-phase (just `3.1`). The purpose of sub-phases is to make the user's review manageable, not to inflate the plan. When in doubt, fewer sub-phases is better.

**Task grouping (parallel execution)**: Tasks within a sub-phase that don't conflict MUST be assigned the same `group` field so they execute in parallel. Only use sequential (different groups or no group) when tasks have real dependencies — e.g., test engineer waits for engineer to finish. The diagram renders grouped tasks as fork/join. Example:
```json
{
  "tasks": [
    {"title": "Add UserService", "agent": "middle-backend-engineer", "group": "impl"},
    {"title": "Add OrderService", "agent": "middle-backend-engineer", "group": "impl"},
    {"title": "Write UserService tests", "agent": "middle-backend-test-engineer", "group": "test"},
    {"title": "Write OrderService tests", "agent": "middle-backend-test-engineer", "group": "test"}
  ]
}
```
Here `impl` tasks run in parallel, then `test` tasks run in parallel after. Without groups, all 4 would run sequentially — wasteful when they don't conflict.

**Scope (must vs may)**: Call `workspace_set_scope` alongside the plan. The distinction matters:
- **must**: Broad areas where absence of changes means the task is incomplete. These are ticket-level requirements obvious *before* planning — e.g., if the ticket says "add BDD scenarios", the BDD module is must-scope. Keep this list short.
- **may**: Specific files and packages identified *during* planning. Most paths from the execution plan belong here. These are permitted but not required — the plan proposes them, but the user decides if they're all necessary.

When plan is agreed:
1. Call `workspace_set_scope` with must/may paths
2. Call `workspace_set_plan` with the full plan JSON
3. Call `workspace_update_progress` for phase `"3"`
4. Call `workspace_advance`

**Extending the plan later**: If during execution the user requests additional changes within the same ticket, or new work is discovered that warrants a new sub-phase, use `workspace_extend_plan` instead of rewriting the entire plan with `workspace_set_plan`. This appends a new sub-phase (auto-assigned ID, with scope) without touching existing sub-phases — fewer tokens, less risk of breaking the plan. The plan and scope statuses are set to 'pending' (user must re-approve).

**Advance 3.0 → 3.1** requires: valid plan with ≥1 execution sub-phase + progress entry `"3"`.

---

## Phase 3.1: Plan Review (USER GATE)

User reviews the plan, scope, and system diagram in the admin panel.

- **Approve** → advances to `3.1.0`
- **Reject** → back to `3.0` with comments

Poll `workspace_get_state` once per minute. After 10 polls, ask user in chat.

**After rejection**: the backend sets the phase to `3.0`. Do NOT call `workspace_advance` immediately. Instead:
1. Call `workspace_get_state` to confirm you're at `3.0`
2. Call `workspace_get_comments` to read the rejection feedback
3. Message plan-advisor via `SendMessage(to: "plan-advisor", ...)` with the feedback to revise the plan
4. Call `workspace_set_plan` and `workspace_set_scope` with the revised plan
5. Call `workspace_advance` only after the plan is updated

---

## Agent Selection Matrix

When assigning tasks to agents, use this decision matrix:

| Task type | Agent | Never assign to |
|-----------|-------|-----------------|
| Production code (CRUD, services, configs) | `middle-backend-engineer` | test engineers |
| Complex production code (vague specs, unknown root cause) | `senior-backend-engineer` | test engineers |
| Tests for new/changed code | `middle-backend-test-engineer` | backend engineers |
| Complex test scenarios (edge cases, integration) | `senior-backend-test-engineer` | backend engineers |
| Code quality review | `middle-code-validator` or `senior-code-validator` | — |

**Critical rule: Tests MUST be written by a separate test engineer agent, NEVER by the same agent that implemented the production code.** The implementing agent is not objective — they will test what they think the code does, not what it should do. Test engineers review the implementation with fresh eyes and write tests that validate behavior independently.

**Execution order within a sub-phase:**
1. Deploy backend engineer(s) for production code
2. Deploy test engineer(s) for tests — AFTER the production code is written
3. Both share the same sub-phase scope; test engineer reads the implementation to understand what to test

When planning tasks in phase 3.0, structure each sub-phase with separate tasks for implementation and testing, assigned to the appropriate agent types. Never create a single task that asks an engineer to "implement + write tests".

---

## Phase 3.N.0: Implementation

**Actors**: Engineer sub-agents, then test engineer sub-agents | **Code edits: ON (in sub-phase scope)**

Deploy in two stages:

**Stage 1 — Production code**: Deploy engineer sub-agent(s) for the implementation tasks.

**Stage 2 — Tests**: After engineers complete, deploy test engineer sub-agent(s) to write tests for the new/changed code. Test engineers read the implementation but write tests independently — they are NOT briefed on "how the code works", only on "what it should do" (from the task description and scope).

If during implementation an issue arises that requires changing the approach or scope, message the plan-advisor teammate to discuss:

```
SendMessage(
  to: "plan-advisor",
  content: "Implementation issue in sub-phase {N}: {describe the problem}.
            The original plan assumed {X} but we found {Y}. What's the best path forward?"
)
```

If the user requests additional work or new requirements emerge, use `workspace_extend_plan` to add a new sub-phase rather than rewriting the entire plan. This preserves existing sub-phases and their progress.

Call `workspace_advance` when both implementation and tests are complete.

**Advance 3.N.0 → 3.N.1** requires: at least 1 file changed per `must`-scope entry.

---

## Phase 3.N.1: Validation

**Actors**: Validator sub-agents | **Code edits: OFF**

Deploy validator sub-agents: compilation check + code quality review. Results stored in `workspace/validation/3.N.json`.

Call `workspace_advance`. Backend auto-routes:
- Issues found → `3.N.2` (Fixes)
- Clean → `3.N.3` (Code Review)

---

## Phase 3.N.2: Fixes

**Actors**: Engineer sub-agents | **Code edits: ON (in sub-phase scope)**

You arrive here from validation failures OR user gate rejections. Read `workspace_get_comments` for user feedback. Deploy engineer sub-agents to fix the issues. Call `workspace_advance` when done.

---

## Phase 3.N.3: Code Review (USER GATE)

User reviews the diff in the admin panel.

- **Approve** (+ optional commit message) → `3.N.4`
- **Reject** → back to `3.N.2` with comments

Poll `workspace_get_state` once per minute. After 10 polls, ask user in chat.

**After rejection**: the backend sets the phase to `3.N.2`. You are now in the fix phase — code edits are ON. Do NOT call `workspace_advance` immediately. Instead:
1. Call `workspace_get_state` to confirm you're at `3.N.2`
2. Call `workspace_get_comments` to read the rejection feedback
3. Deploy engineer sub-agents to address the feedback
4. Call `workspace_advance` only after fixes are complete

---

## Phase 3.N.4: Commit

**Actor**: Engineer sub-agent | **Commits: ON**

Commit all changes. Use the commit message from `workspace_get_state` (`context.commit_message`) or generate one per git-rules.md.

Call `workspace_advance(commit_hash="{hash}")`.

**Advance 3.N.4 → next** requires: valid commit hash + progress entry `"3.N"`. Backend routes to `3.(N+1).0` or `4.0` if last sub-phase.

---

## Phase 4.0: Blind Code Review

**Actors**: Fresh reviewer sub-agents (zero implementation context) | **Code edits: OFF**

Deploy code-reviewer sub-agents. Do NOT brief reviewers with implementation context — they must review the code blind.

Reviewers submit findings via `workspace_submit_review_issue(file_path, line_start, line_end, severity, description)`. Only `critical` and `major` severity findings are accepted — lower severity is rejected by the server.

Each submitted finding creates a review discussion with `resolution='open'`.

Call `workspace_advance`.

**Advance 4.0 → 4.1** requires: progress entry for phase `"4.0"`.

---

## Phase 4.1: Address & Fix

**Actors**: Engineer sub-agents | **Code edits: ON (merged scope), Commits: ON**

Active scope = union of all sub-phase scopes.

1. Read review items via `workspace_get_review_issues`
2. Address each finding — fix the code, or determine it's a false positive / out of scope
3. Set resolution via `workspace_resolve_review_issue(issue_id, "fixed"|"false_positive"|"out_of_scope")`
4. The user reviews resolutions in the admin panel and resolves each item

**Important**: Agents set the `resolution` but cannot resolve items. Only the user can resolve review items (set `status='resolved'`) via the admin panel. The `ReviewGuard` blocks advancement until ALL scope='review' discussions are user-resolved.

When complete:
1. Call `workspace_update_progress` for phase `"4"`
2. Call `workspace_advance`

**Advance 4.1 → 4.2** requires: progress entry `"4"` + all review items resolved by user.

---

## Phase 4.2: Final Approval (USER GATE)

- **Approve** → `5`
- **Reject** → back to `4.1`

Poll `workspace_get_state` once per minute. After 10 polls, ask user in chat.

**After rejection**: the backend sets the phase to `4.1`. Do NOT call `workspace_advance` immediately. Instead:
1. Call `workspace_get_state` to confirm you're at `4.1`
2. Call `workspace_get_comments` to read the rejection feedback
3. Address the feedback — fix code, update resolutions
4. Call `workspace_advance` only after fixes are complete

---

## Phase 5: Done

Push and MR/PR creation allowed. Task complete.

---

## Edits & Commits Matrix

| Phase | Code Edits | Commits | Push/MR |
|-------|-----------|---------|---------|
| 0–1, 2.0–2.1, 3.0–3.1 | OFF | OFF | OFF |
| 3.N.1, 3.N.3 | OFF | OFF | OFF |
| **3.N.0, 3.N.2** | **ON (in scope)** | OFF | OFF |
| **3.N.4** | OFF | **ON** | OFF |
| 4.0 | OFF | OFF | OFF |
| **4.1** | **ON (merged scope)** | **ON** | OFF |
| 4.2 | OFF | OFF | OFF |
| **5** | OFF | OFF | **ON** |

---

## User Gate Rejection — Critical Rule

**When a user gate rejects, the backend moves you to the fix/rework phase. You MUST fix before advancing.**

| Gate | On reject, phase becomes | What to do |
|------|--------------------------|------------|
| 3.1 (Plan Review) | `3.0` | Read comments, revise plan, then advance |
| 3.N.3 (Code Review) | `3.N.2` | Read comments, fix code, then advance |
| 4.2 (Final Approval) | `4.1` | Read comments, fix code, then advance |

**NEVER call `workspace_advance` immediately after detecting a rejection.** Always: (1) read `workspace_get_state` to confirm the new phase, (2) read `workspace_get_comments` for feedback, (3) do the work, (4) then advance.

---

## Review Item Resolution Flow

Review items (scope='review' discussions) follow a two-step lifecycle:

1. **Agent sets resolution**: After addressing a finding, call `workspace_resolve_review_issue(id, "fixed"|"false_positive"|"out_of_scope")`. This marks what the agent did but does NOT resolve the item.
2. **User resolves**: At the code review gate (3.N.3) or final approval (4.2), the user reviews resolutions and resolves each item in the admin panel.

The `ReviewGuard` only blocks at user gate phases (3.N.3, 4.2) — it does NOT block during implementation or fixes. The agent can freely advance from 3.N.2 (Fixes) to 3.N.3 (Code Review) with unresolved items. The user resolves them during review.

---

## Advance Error Handling

| Code | Meaning |
|------|---------|
| 200 | Advanced |
| 202 | User gate — poll and wait |
| 422 | Validation failed — read error, fix, retry |
| 409 | Already at gate or phase changed |

On 422: read the error message. It names exactly what is missing. Fix it, then call `workspace_advance` again.

---

## Progress Documentation

Required before certain advances. Use `workspace_update_progress`:

| Advance | Requires progress for |
|---------|----------------------|
| 1 → 2.0 | `"1"` |
| 2.1 → 3.0 | `"2"` |
| 3.0 → 3.1 | `"3"` |
| 3.N.4 → next | `"3.N"` |
| 4.1 → 4.2 | `"4"` |

Progress is used for phase gate validation, session recovery after compaction, and retrospective review.
