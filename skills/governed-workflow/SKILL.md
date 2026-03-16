---
name: governed-workflow
description: Orchestrates a governed multi-phase implementation workflow — assessment, research, planning, execution, review, and delivery — with backend-enforced phase gates, scope locking, and proof-driven research.
---

# Governed Workflow Skill

Multi-phase implementation workflow with backend-enforced transitions. Every phase advance is validated server-side — the orchestrator cannot self-certify readiness.

**Start every session by calling `workspace_get_state`.** The `phase` field tells you where you are. The `previous_sessions` field tells you whether this is a fresh start or a continuation.

---

## Agent Roles: Teammates vs Sub-agents

| Kind | Spawned via | Persists | Resumed via |
|------|-------------|----------|-------------|
| **Teammate** | `Agent` tool with `run_in_background: true` | Yes — lives for the full session | `resume` parameter with stored agent ID |
| **Sub-agent** | `Agent` tool without background flag | No — returns result, then terminates | N/A |

### Spawn rules per role

| Role | Spawn as | When |
|------|----------|------|
| **plan-advisor** | **TEAMMATE** (always) | Phase 0, resumed in phases 1, 3, 3.N.0 |
| senior-backend-engineer | teammate or sub-agent | Use teammate for complex sub-phases that span 3.N.0 → 3.N.2 fix cycles. Production code ONLY — never tests. |
| senior-backend-test-engineer | teammate or sub-agent | Use teammate for complex test scenarios spanning write + fix cycles. Tests ONLY — always deployed AFTER engineer completes. |
| senior-code-validator | teammate or sub-agent | Use teammate when re-validation after fixes is expected |
| senior-code-researcher | teammate or sub-agent | Use teammate for deep research spanning multiple rounds |
| researcher (middle) | sub-agent | Phase 2.0 (parallel, one per topic) |
| research-prover | sub-agent | Phase 2.1 |
| engineer (middle) | sub-agent | Phases 3.N.0 (stage 1), 3.N.2, 3.N.4, 4.1. Production code ONLY — never tests. |
| test engineer (middle) | sub-agent | Phase 3.N.0 (stage 2, after engineer). Tests ONLY. |
| validator (middle) | sub-agent | Phase 3.N.1 |
| reviewer | sub-agent | Phase 4.0 |

**The plan-advisor is ALWAYS a teammate — NEVER a sub-agent.** It is spawned once in Phase 0 with `run_in_background: true` and resumed via `resume: {plan_advisor_id}` in every subsequent phase that needs it.

**Senior agents**: decide based on task complexity. If the task is complex enough that the agent will need persistent context across multiple phases or fix cycles, spawn as a teammate. For one-shot work, a sub-agent is fine. Middle-level agents are always sub-agents.

All teammates are spawned with `run_in_background: true` and resumed via `resume: {agent_id}`. Store every teammate's agent ID when spawned.

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
| `workspace_submit_review_issue` | Submit a review finding with file/line location (critical/major only) |
| `workspace_get_review_issues` | Get all review items, optionally filtered by resolution status |
| `workspace_resolve_review_issue` | Set resolution on a review item (fixed, false_positive, out_of_scope) |

---

## Session Start / Recovery

**Every session — fresh or resumed — starts here:**

1. Call `workspace_get_state`
2. Read `phase` and `previous_sessions`

**Fresh start** (`phase == "0"` and `previous_sessions` is empty): proceed to Phase 0.

**Recovery** (`phase > "0"` or `previous_sessions` is non-empty): the previous session ended (compaction, restart, or manual resume). **All teammates from the previous session are gone — you MUST re-spawn them.**

1. Read `progress` entries to reconstruct what happened
2. **IMMEDIATELY re-spawn the plan-advisor teammate** (phase >= 1):
   ```
   Agent(
     subagent_type: "co-pilot",
     model: "opus",
     run_in_background: true,
     prompt: "You are the plan-advisor teammate in this governed workflow session.
              Workspace: {working_dir}
              Wait for instructions from the orchestrator."
   )
   ```
3. Store the new agent ID as `plan_advisor_id` for all future resume calls
4. Continue from the current phase

---

## Phase 0: Init — Spawn the Team

**Actors**: Orchestrator

The workspace already exists (created via admin panel). This phase sets up the persistent team.

### Steps

1. Spawn `plan-advisor` as a **background teammate**:

```
Agent(
  subagent_type: "general-purpose",
  model: "opus",
  run_in_background: true,
  prompt: "You are the plan-advisor teammate in this governed workflow session.
           Read and follow: ~/.claude-assistant/agents/plan-advisor.md
           Workspace: {working_dir}
           Your role: assess the codebase, advise on planning, review the execution plan.
           Wait for instructions from the orchestrator."
)
```

2. Store the returned agent ID as `plan_advisor_id`. You will use it for every future `resume` call to this teammate.

3. Call `workspace_advance` to move to phase 1.

**The plan-advisor teammate is NOT terminated between phases. It persists until the session ends.**

---

## Phase 1: Assessment

**Actor**: plan-advisor **teammate** (resumed — NOT a new sub-agent)

If you don't have `plan_advisor_id` yet (skipped Phase 0 or session recovery), spawn the teammate first (see Phase 0 steps), then resume it.

Resume the plan-advisor teammate:

```
Agent(
  resume: {plan_advisor_id},
  prompt: "Begin assessment. Read workspace_get_state for context (ticket, working_dir, context notes).
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

Resume the plan-advisor teammate and collaborate on the execution plan:

```
Agent(
  resume: {plan_advisor_id},
  prompt: "We are in the planning phase. Review the research findings via workspace_get_state.
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
3. Resume plan-advisor with the feedback to revise the plan
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

If during implementation an issue arises that requires changing the approach or scope, resume the plan-advisor teammate to discuss:

```
Agent(
  resume: {plan_advisor_id},
  prompt: "Implementation issue in sub-phase {N}: {describe the problem}.
           The original plan assumed {X} but we found {Y}. What's the best path forward?"
)
```

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
