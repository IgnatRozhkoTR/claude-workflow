---
name: planning
description: Guides the orchestrator through Phase 2.0 (Planning) of the governed workflow — structuring the execution plan, defining scope, proposing acceptance criteria, and collaborating with the plan-advisor teammate.
---

# Planning Skill

Phase 2.0 of the governed workflow. The orchestrator and plan-advisor teammate collaborate to produce an execution plan, scope definition, and acceptance criteria. The plan must pass backend validation and user review before execution begins.

---

## Plan Structure

The execution plan has two audiences: **the user** (who reviews it in the admin panel) and **the agents** (who execute it). Structure accordingly.

### Plan description

The `description` field is a paragraph answering four questions:

1. **What** are we building?
2. **Why** — motivation from the ticket
3. **How** — high-level approach (not implementation details, but the architectural direction)
4. **What is out of scope** — explicitly state boundaries

This paragraph is the first thing the user reads. Keep it under 5 sentences. No class names, no file paths.

### Sub-phases

Each sub-phase has `id`, `name`, and `tasks`. Sub-phases map to execution cycles (3.1, 3.2, ...) — each goes through implementation, validation, review, and commit.

**Splitting into sub-phases is NOT required.** A single sub-phase (`3.1`) is the default. Only split when:

- The task has **large, independently reviewable parts** — e.g., backend feature implementation, frontend UI, and BDD scenarios are three distinct review scopes that benefit from separate commits and reviews.
- Each part is **self-contained enough** to be reviewed on its own — it compiles, tests pass, and the reviewer can understand the change without seeing the other sub-phases.

**Do NOT split when:**
- Two changes depend on each other (e.g., an entity and the service that uses it) — these belong in the same sub-phase even if they're in different files.
- The split would create sub-phases so small they don't warrant independent review.
- You're splitting just to organize by file or class — that's what tasks within a sub-phase are for.

**The litmus test: will the reviewer get lost?** If the combined diff would be large and span multiple concerns, split it. If the reviewer can follow the changes as a single coherent unit, keep it together. The purpose of sub-phases is to make review manageable — don't avoid splitting when the review genuinely needs it, but don't inflate the plan either.

### Tasks — two-layer structure

Every task has a human layer and an agent layer:

- **`title`**: Human-readable summary. One sentence describing WHAT this step does at a business level. No class names, no method names, no parameter values. The user reads this to understand the plan at a glance.
  - Good: "Create the service that generates default narrative segments from a chapter template"
  - Bad: "Create NarrativeService with getTemplate(), saveTemplate(), generateDefault()"

- **`description`**: Technical specification for the implementing agent. Class names, method signatures, parameter values, file paths, API contracts, edge cases to handle. This is the agent's work order — it must contain everything the agent needs to do the work without guessing.
  - Example: "NarrativeService with methods getTemplate(UUID chapterId), saveTemplate(NarrativeTemplate), generateDefault(UUID chapterId), regenerateSegment(UUID segmentId). Hardcoded taxonomy version = 2023-12-22. Use JmixDataRepository for persistence. Return Optional where absence is possible."

- **`files`**: Array of file paths the task will touch. Used for scope enforcement and parallel conflict detection.

- **`agent`**: Agent type to assign. See the agent selection matrix in the main SKILL.md.

- **`group`**: Optional. Tasks with the same group name run in parallel (fork/join). Tasks without a group or with unique group names run sequentially. Groups execute in order of first appearance within the sub-phase.

- **`status`**: Always `"pending"` at plan creation.

**Separation rule**: Never combine "implement + write tests" into a single task. Production code and test code are always separate tasks assigned to different agent types.

### System diagrams

Required for every plan. The `systemDiagram` field is an array of Mermaid diagrams:

1. **Class/entity diagram** (required): Key classes, entities, or components and their relationships. Use Mermaid `classDiagram` syntax.
2. **Sequence diagram(s)** (required): Control flow through the system for the main use cases. Use Mermaid `sequenceDiagram` syntax. Create one diagram per distinct flow — multiple sequence diagrams are encouraged when the feature involves multiple user-facing flows.

Format:
```json
"systemDiagram": [
  {"title": "Class Diagram", "diagram": "classDiagram\n  class UserService {\n    +createUser()\n  }"},
  {"title": "Auth Flow", "diagram": "sequenceDiagram\n  Client->>+API: POST /login\n  API->>+UserService: authenticate()"}
]
```

---

## Scope Definition

Scope is defined per sub-phase as a phase-keyed map, set via `workspace_set_scope`. The distinction between `must` and `may` matters for enforcement:

- **must**: Broad areas where absence of changes means the task is incomplete. These are ticket-level requirements obvious before planning. Keep this list short — if the ticket says "add BDD scenarios", the BDD module is must-scope.

- **may**: Specific files and packages identified during planning. Most paths from the execution plan belong here. These are permitted but not required — the plan proposes them, but the user decides if they are all necessary.

Format:
```json
{
  "3.1": {"must": ["src/main/java/**/entity/"], "may": ["src/main/resources/db/changelog/"]},
  "3.2": {"must": ["src/main/java/**/service/"], "may": ["src/main/java/**/util/"]}
}
```

Each key is a sub-phase ID matching the plan's execution items. During execution, the hook enforces the current sub-phase's scope automatically. When the plan is approved at phase 2.1, the scope is approved together with it. No separate scope proposal per sub-phase is needed later.

For test-type acceptance criteria, add the test file paths to the relevant sub-phase's must-scope.

---

## Acceptance Criteria

Acceptance criteria are validated programmatically when the last sub-phase commits. If any accepted criterion with a validator fails, advancement to review is blocked.

### Reviewing existing criteria

Call `workspace_get_state` and read the `acceptance_criteria` field. The user may have defined criteria during workspace setup. Review them for completeness — do they cover the ticket's requirements?

### Proposing additional criteria

Call `workspace_propose_criteria` for any gaps. Supported types:

**For `unit_test` or `integration_test`:**
```
workspace_propose_criteria(
  type="unit_test",
  description="UserService creation and validation logic",
  details_json='{"file": "src/test/java/com/example/UserServiceTest.java", "test_names": ["createUser_shouldReturnUser_whenValid", "createUser_shouldThrow_whenEmailTaken"]}'
)
```

**For `bdd_scenario`:**
```
workspace_propose_criteria(
  type="bdd_scenario",
  description="User registration end-to-end flow",
  details_json='{"file": "features/user-registration.feature", "scenario_names": ["User registers with valid data", "User sees error for duplicate email"]}'
)
```

**For `custom`:**
```
workspace_propose_criteria(
  type="custom",
  description="Liquibase changelog applies cleanly",
  details_json='{"instruction": "Run liquibase update and verify no errors on a clean database"}'
)
```

**IMPORTANT**: The `details_json` parameter must be a JSON-encoded STRING, not a dict object. Always use `json.dumps()` or construct the string manually.

### Gate rule

All acceptance criteria must be accepted (or deleted) before the plan can advance to user review. Criteria with status `proposed` or `rejected` will block advancement.

---

## Collaboration with Plan-Advisor

The plan-advisor is a persistent teammate, not a sub-agent. It was spawned in Phase 0 and must be resumed, never re-spawned.

### Step 1 — Resume and present

Resume the plan-advisor with a high-level plan outline:

```
Agent(
  resume: {plan_advisor_id},
  prompt: "We are in the planning phase. Review the research findings via workspace_get_state.
           Here is my proposed plan outline:
           {outline — sub-phases, task summaries, scope boundaries}
           Review every task: agent selection, file scope, task clarity, dependencies, gaps.
           Send your review as a numbered list with verdict per task (OK or CONCERN)."
)
```

### Step 2 — Review and discuss

The plan-advisor reviews every task and sends a numbered list with verdicts. For each concern:
- Accept and adjust the plan, OR
- Reject with reasoning

Discuss until consensus on each point.

### Step 3 — Expansion

After consensus, the plan-advisor expands the plan with technical details (class names, method signatures, file paths in task descriptions).

### Step 4 — Orchestrator review

Review the expansion. Send numbered remarks on specific tasks if needed. The plan-advisor responds and adjusts. **One round maximum**, then finalize.

### Step 5 — Finalize

Execute in order:
1. `workspace_set_scope` — phase-keyed scope map (one entry per sub-phase)
2. `workspace_set_plan` — full plan JSON (execution items define tasks, NOT scope)
3. `workspace_update_progress` for phase `"2"` with a summary of the plan
4. `workspace_advance`

**Advance 2.0 -> 2.1** requires: valid plan with at least 1 execution sub-phase + progress entry `"2"`.

---

## Anti-patterns

| Do NOT | Instead |
|--------|---------|
| Stuff technical details into task titles | Titles are for humans — keep them business-level |
| Create a sub-phase per file | Sub-phases are for logical chunks — layers, modules, concerns |
| Inflate the plan with unnecessary sub-phases | Fewer sub-phases is better; one is fine for simple tasks |
| Skip acceptance criteria | They are validated programmatically — missing criteria means gaps slip through |
| Combine "implement + write tests" in one task | Always separate — different agents, different perspectives |
| Use `proposed` or `rejected` criteria status at advance time | All criteria must be `accepted` or deleted before advancing |
| Brief the plan-advisor with implementation assumptions | Present the outline, let the advisor form independent judgment |
| Pass `details_json` as a dict object | It must be a JSON-encoded string |
