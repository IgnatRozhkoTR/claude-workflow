---
name: stride
description: Structured implementation approach for complex tasks
user_invocable: true
---

# Stride

Lightweight structured workflow for complex tasks. No admin panel, no MCP tools — the agent manages everything in conversation. Same phases and agent roles as the governed workflow, but the agent self-advances through all gates except Plan Review, which requires user approval.

Follow the phases sequentially. State which phase you're in at each step.

---

## Phase 0: Init — Spawn the Team

**Actor**: Orchestrator

Spawn the plan-advisor as a **background teammate** — it persists across all phases:

```
Agent(
  subagent_type: "plan-advisor",
  model: "opus",
  run_in_background: true,
  prompt: "You are the plan-advisor teammate in this stride session.
           Working directory: {working_dir}
           Your role: assess the codebase, advise on planning, review the execution plan.
           Wait for instructions from the orchestrator."
)
```

Store the returned agent ID as `plan_advisor_id`. You will resume this teammate throughout the session.

---

## Agent Roles

| Role | Spawn as | Purpose |
|------|----------|---------|
| **plan-advisor** | **TEAMMATE** (always background) | Assessment, planning advice, issue resolution |
| code-researcher / senior-code-researcher | sub-agent | Research — one per topic, parallel |
| middle-backend-engineer / senior-backend-engineer | sub-agent | Production code ONLY — never tests |
| middle-backend-test-engineer / senior-backend-test-engineer | sub-agent | Tests ONLY — always AFTER engineer completes |
| middle-code-validator / senior-code-validator | sub-agent | Validation — code quality review |
| code-reviewer | sub-agent | Phase 4.0 blind review |

**Critical rules:**
- **Engineers NEVER write tests.** Test engineers NEVER write production code.
- **Test engineers are deployed AFTER engineers complete**, so they review the implementation with fresh eyes.
- **The plan-advisor is ALWAYS a teammate** — spawned once, resumed via `resume: {plan_advisor_id}`.

---

## Phase 1.0: Assessment

**Actor**: plan-advisor **teammate** (resumed)

Resume the plan-advisor:
```
Agent(
  resume: {plan_advisor_id},
  prompt: "Begin assessment. Read the user's request. Explore the codebase — find relevant files,
           understand patterns and conventions.

           Produce a structured assessment covering:
           - Ticket restatement: rephrase the request in your own words to confirm understanding
           - Affected areas: concepts involved — APIs, user flows, data pipelines (not just file paths)
           - API impact: which endpoints change, what contract changes are expected
           - Data flow: where key values originate and how they move through the system
           - Ticket gaps: what is underspecified or ambiguous in the request
           - Dependencies: which other modules or consumers depend on what we're changing
           - Research questions: what needs deeper investigation before planning

           Report all of the above."
)
```

**Output**: Structured assessment covering all points above.

---

## Phase 1.1: Research

**Actors**: Researcher sub-agents (parallel, one per topic)

Deploy parallel researcher sub-agents — one per question from assessment:

```
Agent(
  subagent_type: "code-researcher",
  prompt: "Research topic: {question}
           Working directory: {working_dir}
           Investigate thoroughly — read all relevant files, trace code paths.
           Return: topic, summary (2-3 sentence human-readable overview of what you found),
           findings with file:line evidence."
)
```

Launch all researchers in a single message for parallel execution. Use `senior-code-researcher` for topics requiring deep cross-component analysis.

**Output**: Per topic — summary + findings with file:line references.

---

## Phase 1.2: Research Proving

**Verify your own research findings.**

For each finding from 1.1, confirm the evidence is real:
- Code references: re-read the file, verify the lines match what was claimed
- If a finding's proof doesn't hold, re-deploy the researcher for that topic

Don't skip this — false research leads to bad plans.

**Output**: Confirmed findings (drop or re-research anything unproven).

---

## Phase 1.3: Impact Analysis

**Identify impacts beyond the immediate code changes.**

Produce a structured impact analysis covering:
- **Affected user flows**: which UI paths, API calls, or integrations are touched
- **API contract changes**: request/response shape changes, new fields, removed fields, behaviour shifts
- **Data flow changes**: how data movement through the system changes as a result
- **External dependencies**: DB migrations, infrastructure changes, coordination with other teams or services
- **Ticket gaps found**: ambiguities or missing details uncovered during research
- **Remaining open questions**: anything still unresolved that may affect planning

If impact analysis reveals new gaps, deploy additional researchers before proceeding.

**Output**: Structured impact analysis covering all points above.

---

## Phase 1.4: Present Findings

### >>> STOP — present findings and wait for user confirmation.

Present to the user:
- Research summaries (one per topic)
- Impact analysis
- Open questions that need user input
- Proposed research topics if any remain

Do NOT proceed to planning until user confirms. If user identifies gaps, go back to research.

---

## Phase 2.0: Planning

**Actors**: Orchestrator + plan-advisor teammate

Resume the plan-advisor:
```
Agent(
  resume: {plan_advisor_id},
  prompt: "Planning phase. Review the research findings.
           Help design the execution plan. Consider whether this needs multiple sub-phases
           or a single one. Each sub-phase needs: name, scope (must/may file patterns), tasks
           (separate tasks for production code and tests), test plan."
)
```

Structure the work into sub-phases (3.1, 3.2, ...). For simple tasks, a single sub-phase is fine.

Each sub-phase needs:
- **Name**: what's being built
- **Scope**: which files/directories will be touched (must-change vs may-change)
- **Tasks**: ordered list — separate entries for production code and tests, assigned to appropriate agent types
- **Test plan**: what to test, which test files

**Sub-phase count guidance**: Don't inflate. Multiple sub-phases only when the task naturally splits into independent chunks. Fewer is better.

**Task grouping (parallel execution)**: Tasks within a sub-phase that don't conflict MUST share the same group name so they execute in parallel (launched in a single message). Only separate into sequential groups when there's a real dependency — e.g., test engineers wait for engineers. Default assumption: independent tasks are parallel unless proven otherwise.

### >>> STOP — present the plan and wait for user approval.

Do NOT implement until user confirms. If user requests changes, revise and re-present.

---

## Phase 3.N.0: Implementation

**Actors**: Engineer sub-agents (stage 1), then test engineer sub-agents (stage 2)

For each sub-phase N, deploy in two stages:

**Stage 1 — Production code**: Launch all engineer sub-agents for the same group in a single message (parallel):
```
Agent(
  subagent_type: "middle-backend-engineer",
  prompt: "Implement task: {task_1_description}
           Working directory: {working_dir}
           Scope: {must and may patterns}
           Do NOT write tests — a separate test engineer handles that."
)
Agent(
  subagent_type: "middle-backend-engineer",
  prompt: "Implement task: {task_2_description}
           Working directory: {working_dir}
           Scope: {must and may patterns}
           Do NOT write tests — a separate test engineer handles that."
)
```

**Stage 2 — Tests** (after engineer completes):
```
Agent(
  subagent_type: "middle-backend-test-engineer",
  prompt: "Write tests for the changes in sub-phase {N}.
           Working directory: {working_dir}
           Read the implementation to understand what changed, then write tests independently.
           You are NOT briefed on how the code works — only on what it should do: {task descriptions}"
)
```

Use senior variants for complex work. If something unexpected comes up, resume the plan-advisor to discuss.

---

## Phase 3.N.1: Validation

**Actors**: Validator sub-agents

Deploy a validator:
```
Agent(
  subagent_type: "middle-code-validator",
  prompt: "Validate the implementation of sub-phase {N}.
           Working directory: {working_dir}
           Check: syntax, imports, conventions, error handling, all code paths implemented,
           no placeholders, no TODOs, no debug prints. Run tests."
)
```

If issues found → Phase 3.N.2 (Fixes). If clean → next sub-phase or Phase 4.0.

---

## Phase 3.N.2: Fixes

**Actors**: Engineer sub-agents

Fix validation issues, then re-validate (loop back to 3.N.1).

---

## Phase 4.0: Final Review

**Actors**: Fresh code-reviewer sub-agents (zero implementation context)

Deploy a blind reviewer — do NOT brief with implementation details:
```
Agent(
  subagent_type: "code-reviewer",
  prompt: "Review all changes in this session. Working directory: {working_dir}
           You have zero implementation context — review the code blind.
           Check: correctness, edge cases, error handling, naming, patterns, test coverage.
           Report issues with file:line locations and severity (critical/major only)."
)
```

Collect the findings.

---

## Phase 4.1: Address Fixes

**Actors**: Engineer sub-agents

For each review finding:
1. Fix the code, or determine it's a false positive / out of scope
2. Note the resolution for each finding

Re-run tests after fixes.

---

## Phase 5: Delivery

### >>> STOP — present summary and wait for user's final review.

Summary format:
- Files modified/created — brief description of each change
- Test results
- Review findings and their resolutions
- Deviations from plan (if any) and why
- Any remaining concerns or follow-up items

---

## Rules

- **State your phase** at the start of each step: `[0 Init]`, `[1.0 Assessment]`, `[3.1.0 Implementation]`, etc.
- **Don't skip phases** — quick assessment prevents mistakes even on simple tasks
- **For trivial fixes** (single obvious line change), say so and ask if user wants the full process
- **The plan is the contract** — don't change scope without flagging it
- **Plan approval and preparation review are the only hard stops** — present and wait before implementing
- **Engineers never write tests, test engineers never write production code**
- **If blocked**, resume the plan-advisor to discuss rather than guessing
- **Keep outputs concise** — bullet points, not essays
