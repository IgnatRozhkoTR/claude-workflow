---
name: plan-preparation
description: Guides the orchestrator through phases 1.0-1.4 of the governed workflow — assessment, research, research proving, impact analysis, and preparation review. Produces a thorough, structured foundation before planning begins.
---

# Plan Preparation Skill

Phases 1.0 through 1.4: take a ticket from raw requirements to a fully researched, impact-analyzed, user-approved foundation ready for planning. Every phase builds on the previous one. No shortcuts — gaps discovered here prevent rework during execution.

---

## Phase 1.0: Assessment

**Actor**: plan-advisor **teammate** (resumed, NOT a new sub-agent)

If you don't have `plan_advisor_id` yet (skipped Phase 0 or session recovery), spawn the teammate first (see Phase 0 in the governed-workflow skill), then resume it.

### Goal

Produce a structured assessment that maps the ticket to the codebase and surfaces everything that needs investigation before planning.

### Prompt

Resume the plan-advisor teammate with an explicit structure requirement:

```
Agent(
  resume: {plan_advisor_id},
  prompt: "Begin assessment. Read workspace_get_state for context (ticket, working_dir, context notes).

           Produce a STRUCTURED assessment with these sections:

           1. TICKET RESTATEMENT — rephrase the ticket in your own words. This catches
              misunderstandings early. If your restatement doesn't match the ticket intent,
              the orchestrator will correct you before research begins.

           2. AFFECTED AREAS — not file paths, but concepts: which APIs, which user flows,
              which data pipelines, which business domains are touched. Think in terms of
              what the system does, not where the code lives.

           3. API IMPACT — which endpoints are created, modified, or removed. What changes
              in request/response contracts. If no API changes, say so explicitly.

           4. DATA FLOW — where do key values come from? Config file? User input? External
              API? Database lookup? Computed at runtime? Trace the origin of every important
              parameter the ticket mentions.

           5. TICKET GAPS — what the ticket doesn't specify. What decisions it leaves to us.
              Be specific: 'ticket says add validation but doesn't specify which fields' is
              useful. 'Ticket could be clearer' is not.

           6. DEPENDENCIES — what other modules, services, or teams consume what we're
              changing. If we modify an API response, who reads it? If we change a DB
              schema, what else queries that table?

           7. RESEARCH QUESTIONS — what needs deeper investigation before we can plan.
              Each question becomes a research topic in phase 1.1. Be specific enough
              that a researcher knows exactly what to look for.

           Raise any discussion points via workspace_post_discussion (type: 'research' for
           questions needing investigation, 'general' for architectural decisions).

           Report your findings in this exact structure."
)
```

### After assessment completes

1. Review the assessment. If the ticket restatement is wrong or incomplete, correct the plan-advisor and have them revise before proceeding.
2. Call `workspace_update_progress` for phase `"1.0"` with a summary covering: ticket restatement, affected areas count, research questions count, and any discussion points raised.
3. Call `workspace_advance`.

**Advance 1.0 -> 1.1** requires: progress entry `"1.0"` with non-empty summary.

---

## Phase 1.1: Research

**Actors**: Researcher sub-agents (parallel, one-shot)

### Goal

Answer every research question from the assessment. Each researcher investigates one topic and saves structured findings with verifiable proofs.

### Deploying researchers

One sub-agent per research question from the assessment. Choose the researcher type based on where the answer lives:

| Answer lives in... | Researcher type | Proof type |
|---------------------|-----------------|------------|
| Codebase (classes, configs, patterns) | `code-researcher` or `senior-code-researcher` | `"code"` |
| External docs, libraries, frameworks | `web-researcher` | `"web"` |
| Git history (when/why something changed) | `diff-researcher` | `"diff"` |

Use `senior-code-researcher` when the topic is complex (deep call chains, framework internals, cross-module interactions). Use `code-researcher` for straightforward lookups (finding classes, checking configs, listing usages).

### Summary requirement

Every researcher MUST provide a `summary` parameter when calling `workspace_save_research`. This is a 2-3 sentence human-readable overview of the overall findings — what was found, what it means for the ticket, and any surprises. The summary appears in research lists and the admin panel without requiring the full findings to be loaded.

Example of a good summary:
> "The TradeService uses Spring's @Transactional with REQUIRES_NEW propagation in 3 of its 14 public methods. This means audit logging within those methods would commit independently of the business transaction — if the trade fails and rolls back, the audit log entry would persist. The remaining 11 methods use default propagation and would roll back audit entries together with the business transaction."

Example of a bad summary:
> "Investigated TradeService transactions. Found several methods with different propagation settings."

### Discussion linking

If a research question originated from a discussion (posted via `workspace_post_discussion` in phase 1.0), pass the `discussion_id` to `workspace_save_research`. This links the research findings to the discussion that raised the question, and is required for advancing past the research phase — all unresolved research discussions must have linked findings.

### Proof format per type

**type: "code"** (code-researcher, senior-code-researcher)
- `file` — path relative to workspace root
- `line_start`, `line_end` — precise proof range (aim for under 20-30 lines)
- `snippet_start`, `snippet_end` — 15-line max window within the proof range for the quick-reference quote
- Do NOT include snippet text — the server reads the actual file to render quotes

**type: "web"** (web-researcher)
- `url` — source URL (required)
- `title` — page/article title
- `quote` — verbatim text from the source (required — server cannot fetch web pages)

**type: "diff"** (diff-researcher)
- `commit` — commit hash (required)
- `file` — specific file in the commit (optional)
- `description` — mandatory context explaining what the diff proves

### When all researchers complete

Call `workspace_advance`.

**Advance 1.1 -> 1.2** requires: at least 1 research entry saved, all entries valid.

---

## Phase 1.2: Research Proving

**Actor**: Prover sub-agent (Opus, one-shot)

### Goal

Verify that every research finding references real, accurate evidence. The prover reads files, checks line numbers, validates commits — it does not research, only verifies.

### Deployment

```
Agent(
  subagent_type: "research-prover",
  prompt: "Verify all research entries for this workspace. Mark each as proven or rejected.
           Workspace: {working_dir}"
)
```

The prover calls `workspace_prove_research` for each entry directly — the orchestrator does NOT need to relay these calls. Wait for the prover to finish, then check results.

### Rejection loop

If any research is rejected:

1. Re-deploy the original researcher sub-agents for those specific topics (to fix their proofs or re-investigate).
2. Re-deploy the prover to verify the corrected entries.
3. Repeat until all research is proven.

Do not advance with rejected research. The loop must converge — if a researcher cannot produce verifiable findings for a topic after 2 attempts, post a discussion via `workspace_post_discussion` noting the gap and move on.

### Handling rejected research

When the prover rejects a research entry:
1. First assess: is the research topic still relevant, or has it become stale/unnecessary?
2. If still relevant: re-deploy the researcher to fix the proofs, then re-prove.
3. If stale or no longer needed: ask the user to delete the research entry via the admin panel (Research tab → delete button). The agent cannot delete research entries — only the user can.
4. All research entries must be either proven or deleted before advancing past 1.2. Rejected entries block advancement.

After 2 failed re-proof attempts for the same topic, treat it as stale and ask the user whether to delete it or provide additional context.

### When all research is proven

1. Call `workspace_update_progress` for phase `"1"` with a summary covering: total research entries, topics investigated, any re-investigations needed, and key findings that affect planning.
2. Call `workspace_advance`.

**Advance 1.2 -> 1.3** requires: all research entries proven + progress entry `"1"`.

---

## Phase 1.3: Impact Analysis

**Actor**: Orchestrator

### Goal

Analyze the proven research findings to identify high-level impacts beyond the immediate code changes. This is where you catch the consequences the ticket doesn't mention — the API contract that breaks, the data pipeline that needs a new field, the team that consumes your output.

### Required analysis structure

Produce a structured analysis covering all six areas:

**1. Affected user flows**
Which user interactions change? Think in terms of what users do, not what code runs. Examples: "The trade creation flow now requires an additional confirmation step", "The report export no longer includes archived trades".

**2. API contract changes**
What changes in request/response formats? New required fields? Removed fields? Changed types? New endpoints? Removed endpoints? Changed authentication requirements? Be specific — "the /api/trades POST response now includes an `auditId` field (string, always present)" is useful. "API changes" is not.

**3. Data flow changes**
Where do key parameters come from and how does data move through the system? Trace the origin and destination of new or changed data. Example: "The audit trail ID is generated by AuditLogService.logAction(), stored in the audit_log table, and returned to the caller in the response. It is NOT passed by the client — it is server-generated."

**4. External dependencies**
Does this require actions outside the codebase? Database migrations not managed by the project, infrastructure changes, Kubernetes config updates, coordination with other teams, third-party API changes.

**5. Ticket gaps found**
Ambiguities and underspecified requirements discovered during research. Each gap should state: what is ambiguous, what the options are, and which option you recommend (with reasoning from research).

**6. Remaining open questions**
Things that need user input because they cannot be resolved from code, web, or git research. These become discussion points for the user at phase 1.4.

### Acceptance criteria review

As part of impact analysis, review existing acceptance criteria:

1. Read `acceptance_criteria` from `workspace_get_state`
2. For each existing criterion: fill in file paths, test names, and refined description via `workspace_update_criteria`
3. Propose additional criteria via `workspace_propose_criteria` if the research reveals gaps the existing criteria don't cover

### Loop logic

Impact analysis may reveal new gaps that need investigation. If this happens:

1. Post new discussion points via `workspace_post_discussion` (type: `"research"`) for the newly discovered questions.
2. Deploy new researcher sub-agents for those topics (same rules as phase 1.1).
3. Deploy prover to verify the new research (same rules as phase 1.2).
4. Re-analyze with the expanded research base.
5. Repeat until all resolvable questions are resolved.

Questions that cannot be resolved from code, web, or git research are left as open questions for the user at phase 1.4. Do not loop indefinitely — if a question requires a human decision, flag it and move on.

### When analysis is complete

1. Call `workspace_set_impact_analysis` with the six structured fields:
   - `affected_flows`: Which user flows change
   - `api_changes`: Endpoint changes and contract changes
   - `data_flow_changes`: Parameter sources and data movement
   - `external_dependencies`: DB migrations, infrastructure, coordination
   - `ticket_gaps`: Ambiguities discovered
   - `open_questions`: Questions for the user

   This data is displayed in the Pre-planning tab for user review at phase 1.4.

2. Call `workspace_update_progress` for phase `"1.3"` summarizing: affected user flows, API changes, data flow changes, external dependencies, ticket gaps with recommendations, and open questions for the user.
3. Call `workspace_advance`.

**Advance 1.3 -> 1.4** requires: progress entry `"1.3"`.

---

## Phase 1.4: Preparation Review (USER GATE)

### Goal

Present the complete preparation to the user for review and approval. The user sees everything discovered during phases 1.0-1.3 and decides whether the foundation is solid enough for planning.

### Presentation

Present to the user via **both** chat and the admin panel pre-planning tab:

**1. Research summaries**
One entry per research topic. Use the `summary` field from each research entry — do not dump full findings. The user can drill into details in the admin panel if needed.

**2. Impact analysis summary**
The six-part analysis from phase 1.3, formatted for readability. Highlight anything that affects scope, timeline, or coordination with other teams.

**3. Open discussions / questions for user**
Questions that could not be resolved from research. Each question should include:
- What was investigated
- What was found (or not found)
- Why a human decision is needed
- Recommended option (if you have one) with reasoning

**4. Resolved discussions**
Discussions that were resolved during research, with brief resolution summaries. This shows the user what was figured out without their input.

### Waiting for approval

Call `workspace_advance` to enter the user gate. Then:

1. Poll `workspace_get_state` once per minute
2. Phase advanced (user approved) -> proceed to phase 2.0 (Planning)
3. After 10 polls -> ask the user in chat
4. User chat message -> re-check state

### On rejection

The user rejected with comments. Their comments guide what needs more work.

1. Read comments via `workspace_get_comments`
2. Determine which phase to revisit:
   - If comments point to missing research -> back to 1.1, deploy researchers for the new topics
   - If comments question the impact analysis -> back to 1.3, re-analyze with user's perspective
   - If comments correct the assessment -> back to 1.0, resume plan-advisor with corrections
3. Re-prove any new research (1.2)
4. Re-analyze impacts if research changed (1.3)
5. Re-present for approval (1.4)

### On approval

Proceed to phase 2.0 (Planning). The preparation is locked — all research, impact analysis, and resolved discussions form the foundation for the execution plan.
