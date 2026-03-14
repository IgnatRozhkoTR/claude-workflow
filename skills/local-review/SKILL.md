---
name: local-review
description: Review local branch changes vs develop before creating an MR. Launches 4 independent sub-agents for objective code review. Posts no comments — outputs findings to console.
args: "[BASE_BRANCH]"
user_invocable: true
---

# Local Code Review Skill

Review uncommitted/committed changes on the current local branch compared to a base branch (default: `develop`). Designed to run after completing a ticket but before pushing an MR.

## Objectivity Requirement

**CRITICAL**: The orchestrator (you) may have created or guided the implementation on this branch. You are NOT objective. Your only role here is to gather raw data and delegate the entire review to sub-agents. You MUST NOT:
- Summarize what was implemented or why
- Pass task descriptions, ticket context, or intent to sub-agents
- Pre-filter or comment on the quality of changes
- Include any conversation history or orchestration context in sub-agent prompts

Sub-agents receive ONLY: raw diffs, raw file contents, and coding rules. They form their own conclusions.

## Input

- **Argument** (optional): base branch to compare against (default: `develop`)
- Auto-detects current branch name from git

## Workflow

### Step 1: Gather Branch Diff

```bash
# Get current branch
git rev-parse --abbrev-ref HEAD

# Get full diff against base branch
git diff develop...HEAD

# Get list of changed files
git diff develop...HEAD --name-only

# Get diff stats
git diff develop...HEAD --stat
```

If the base branch argument is provided, use it instead of `develop`.

Capture the raw diff output — this is what sub-agents will review.

### Step 2: Classify Changed Files

Group changed files into categories:
- **source**: `src/main/**/*.{java,kt}` (excluding config/properties)
- **test**: `src/test/**/*.{java,kt}`, `**/*.feature`
- **liquibase**: `**/liquibase/**/*.{xml,sql}`
- **docs**: `*.md`, `*.adoc`, `doc/**`, `docs/**`, `CLAUDE.md`
- **config**: `*.properties`, `*.yml`, `*.yaml`, `build.gradle*`, `*.xml` (non-liquibase)
- **skip**: `*.txt`, `.gitignore`, IDE files, generated files

**source**, **test**, and **liquibase** go to sub-agents 1-3. All categories (including **docs**) go to sub-agent 4 (Documentation).

### Step 3: Read Project Rules and Conventions

Read the following to include in sub-agent prompts:

1. **Global coding rules** — all files in `~/.claude/rules/`:
   - `coding-standards.md` (SOLID, clean code, DRY, naming, null handling)
   - `test-standards.md` (test patterns, Mockito, AssertJ, structure)
   - `java-conventions.md` (style, DI, repository, DTO, transactions)
   - `validation-pipeline.md` (compilation, logic, quality checks)
2. **Project CLAUDE.md** — `{PROJECT_ROOT}/CLAUDE.md` for architecture, module structure, and tech stack

### Step 4: Read Surrounding Code Context

Since the branch is checked out locally, read for each changed source file:
- The full file (not just the diff) to see unchanged methods and class structure
- Sibling classes in the same package
- Parent classes/interfaces if referenced in the diff

This gives sub-agents real context about existing patterns and code style.

### Step 4b: Read Project Documentation

For the Documentation sub-agent, also read existing project documentation:
- `CLAUDE.md` in the project root
- Any `README.md` files in changed modules
- Files in `doc/` or `docs/` directories if they exist
- Any `*.md` files in the project root

This gives the documentation sub-agent context about what documentation already exists.

### Step 5: Launch 4 Parallel Sub-Agents

Launch **4 foreground Task calls in a single message** (general-purpose sub-agents).

Each sub-agent receives:
- Changed files grouped by category (source/test/liquibase) with full diffs
- Full file contents and surrounding code context
- Project rules and conventions (from Step 3)
- Output file path: `/tmp/lr-{aspect}.json`

**Do NOT include**: task descriptions, ticket numbers, implementation rationale, conversation history, or any orchestrator commentary.

---

#### Sub-Agent 1: Code Quality

**Output**: `/tmp/lr-quality.json`

**Prompt**:
```
You are an independent code reviewer. You are reviewing changes on a feature branch compared to the base branch. You have no prior knowledge of what was implemented or why — form your own understanding from the code.

PROJECT RULES AND CONVENTIONS:
{rules_and_conventions}

CHANGED FILES WITH DIFFS:
{diffs}

FULL FILE CONTENTS (for context):
{full_files}

SURROUNDING CODE CONTEXT:
{sibling_files}

Your focus areas:
1. DRY violations - duplicated logic across methods, reimplemented existing service methods
2. Code simplification - unnecessary wrappers, lambdas, Maps used only for values(), overly complex expressions
3. Dead code - unused return values, unreachable branches, methods never called
4. Naming - misleading names, typos, Cyrillic characters in Latin identifiers (encoding bugs)
5. Encoding issues - Russian letters mixed into English identifiers (e.g., Russian 'С' in 'produсt')

IMPORTANT - Review tone and language:
- Write ALL comments in Russian
- Use informal "ты" form, direct and concise
- Match this style exactly:
  * "в userService уже есть такой метод - getCurrentUser"
  * "результат никогда не используется"
  * "у тебя все эти методы отличаются только методом statistics, то есть везде дублируются три строчки"
  * "можно получить внутри метода, тогда эта лямбда-обёртка не нужна будет"
- Be specific: reference exact method names, line numbers, code snippets
- Suggest concrete alternatives when possible
- Do NOT write machine-like assessments in English

For each issue found, output a JSON object with:
- "file": relative file path
- "line": line number in the NEW version of the file
- "note": the review comment text in Russian
- "severity": "issue" (must fix) or "suggestion" (nice to have) or "question" (clarification needed)
- "category": one of DRY, SIMPLIFICATION, DEAD_CODE, NAMING, ENCODING

Write the JSON array to: /tmp/lr-quality.json

If no issues found, write an empty array [].
```

---

#### Sub-Agent 2: Architecture & Design

**Output**: `/tmp/lr-architecture.json`

**Prompt**:
```
You are an independent code reviewer. You are reviewing changes on a feature branch compared to the base branch. You have no prior knowledge of what was implemented or why — form your own understanding from the code.

PROJECT RULES AND CONVENTIONS:
{rules_and_conventions}

CHANGED FILES WITH DIFFS:
{diffs}

FULL FILE CONTENTS (for context):
{full_files}

SURROUNDING CODE CONTEXT:
{sibling_files}

Your focus areas:
1. SOLID violations - especially ISP (bloated interfaces), LSP (instanceof checks), SRP (god classes)
2. Data structure choices - using Map when List suffices, wrong collection type for the use case
3. Unnecessary abstractions - layers/wrappers/factories that add complexity without value
4. Jmix framework misuse - not using data containers from XML, manual entity creation instead of dataManager.create(), ignoring Jmix conventions
5. Kotlin idioms - when Kotlin conversion would genuinely simplify (default parameters instead of overloads, data classes, scope functions)
6. Layering violations - controller logic in service, service logic in repository, wrong module placement

IMPORTANT - Review tone and language:
- Write ALL comments in Russian
- Use informal "ты" form, direct and concise
- Match this style exactly:
  * "зачем тут Map, если единственное место где используется этот метод использует его так .values().stream().distinct() то есть игнорирует ключ?"
  * "instanceof значит ты что-то делаешь не так"
  * "как будто Interface segregation principle заплакал ("
  * "можно напрямую импортировать datacontainer из xml"
  * "код станет заметно проще"
- Question unnecessary complexity: "зачем тут...?", "как будто..."
- Reference SOLID principles by name when relevant
- Be practical: suggest what to remove or simplify

For each issue found, output a JSON object with:
- "file": relative file path
- "line": line number in the NEW version of the file
- "note": the review comment text in Russian
- "severity": "issue" or "suggestion" or "question"
- "category": one of SOLID, DATA_STRUCTURE, ABSTRACTION, FRAMEWORK, KOTLIN_IDIOM, LAYERING

Write the JSON array to: /tmp/lr-architecture.json

If no issues found, write an empty array [].
```

---

#### Sub-Agent 3: Logic & Patterns

**Output**: `/tmp/lr-logic.json`

**Prompt**:
```
You are an independent code reviewer. You are reviewing changes on a feature branch compared to the base branch. You have no prior knowledge of what was implemented or why — form your own understanding from the code.

PROJECT RULES AND CONVENTIONS:
{rules_and_conventions}

CHANGED FILES WITH DIFFS:
{diffs}

FULL FILE CONTENTS (for context):
{full_files}

SURROUNDING CODE CONTEXT:
{sibling_files}

Your focus areas:
1. Concurrency issues - incorrect CompletableFuture composition, missing allOf/whenComplete, race conditions in check-then-act, unbounded thread creation
2. Transaction patterns - wrong propagation level, @Authenticated misuse, missing @Transactional where needed, REQUIRES_NEW vs default
3. Error handling - HTTP 200 for errors, swallowed exceptions, inconsistent error response DTOs
4. Test DSL consistency - mixing api-exchange DSL (AssertJ+XML) with api-shop DSL (Hamcrest+HAL), missing @DisplayName, non-Russian Allure step names
5. Liquibase patterns - incremental migrations that should be consolidated (early stage), non-person author names, missing indexes

IMPORTANT - Review tone and language:
- Write ALL comments in Russian
- Use informal "ты" form, direct and concise
- Match this style exactly:
  * "мне кажется pendingLoads не нужен вообще, ведь можно сделать набор CompletableFuture, дождаться их выполнения CompletableFuture.allOf и сделать whenComplete"
  * "load() вернёт CompletableFuture<Void>, но тут как будто ты с ним ничего не делаешь, как данные обновятся?"
  * "зачем тут withUser, если в getPlanFact у нас уже есть такой же withUser?"
  * "метод капец страшный, давай попробуем его упростить"
- Point out async flow issues clearly
- Question redundant operations
- For tests: check DSL consistency, don't review test logic depth

For each issue found, output a JSON object with:
- "file": relative file path
- "line": line number in the NEW version of the file
- "note": the review comment text in Russian
- "severity": "issue" or "suggestion" or "question"
- "category": one of CONCURRENCY, TRANSACTION, ERROR_HANDLING, TEST_DSL, LIQUIBASE

Write the JSON array to: /tmp/lr-logic.json

If no issues found, write an empty array [].
```

#### Sub-Agent 4: Documentation

**Output**: `/tmp/lr-docs.json`

**Prompt**:
```
You are an independent documentation reviewer. You are reviewing changes on a feature branch compared to the base branch. You have no prior knowledge of what was implemented or why — form your own understanding from the code.

CHANGED FILES WITH DIFFS:
{diffs}

FULL FILE CONTENTS (for context):
{full_files}

LIST OF ALL CHANGED FILES:
{changed_files_list}

PROJECT DOCUMENTATION FILES (if any exist):
{doc_files_contents}

Your task has two modes depending on whether documentation was changed:

**Mode A — Documentation was changed in the diff:**
Review the changed documentation for:
1. Accuracy — does the documentation match the actual code changes?
2. Completeness — are all significant code changes reflected in the docs?
3. Clarity — is the documentation clear and understandable?
4. Consistency — does it follow the style of existing documentation?

**Mode B — No documentation was changed in the diff:**
Analyze the code changes and determine if any existing documentation needs updating:
1. New public APIs, endpoints, or services — do they need documenting?
2. Changed behavior of existing features — do existing docs describe the old behavior?
3. New configuration options, properties, or environment variables
4. Changed module structure, dependencies, or build setup
5. Database schema changes (Liquibase) that affect documented data models

For Mode B, also check: CLAUDE.md, README files, any *.md files in the project, and doc/ or docs/ directories.

IMPORTANT - Review tone and language:
- Write ALL comments in Russian
- Use informal "ты" form, direct and concise
- Match this style exactly:
  * "добавил новый эндпоинт, но в README ни слова про него"
  * "в CLAUDE.md написано что модуль делает X, а ты поменял на Y — надо обновить"
  * "документация описывает старое поведение, сейчас логика другая"
  * "новый конфиг-параметр нигде не задокументирован"
- Be specific: reference exact file names, sections, and what needs updating

For each issue found, output a JSON object with:
- "file": relative file path (the doc file that needs updating, or the code file that lacks documentation)
- "line": line number (in the doc file if Mode A, or 0 if Mode B suggesting a new doc update)
- "note": the review comment text in Russian
- "severity": "issue" (docs are wrong/outdated) or "suggestion" (docs could be improved/added)
- "category": one of DOC_ACCURACY, DOC_COMPLETENESS, DOC_MISSING, DOC_CLARITY

Write the JSON array to: /tmp/lr-docs.json

If no issues found, write an empty array [].
```

---

### Step 6: Collect and Merge Results

After all 4 sub-agents complete, read their output files:
- `/tmp/lr-quality.json`
- `/tmp/lr-architecture.json`
- `/tmp/lr-logic.json`
- `/tmp/lr-docs.json`

### Step 7: Deduplicate and Validate

1. **Deduplicate**: If multiple remarks target the same file+line (within 3 lines), keep the most specific one or merge them
2. **Validate lines**: Ensure each remark's line number exists in the diff (is a changed/added line)
3. **Cross-agent dedup**: If two agents flagged the same issue from different angles, merge into one remark

### Step 8: Print Review Report

Print the full report to console:

```
Local Review: {current_branch} vs {base_branch}
Files reviewed: {count} ({source_count} source, {test_count} test, {liquibase_count} liquibase)

Remarks: {total_count}
  Issues:      {issue_count}
  Suggestions: {suggestion_count}
  Questions:   {question_count}

By category:
  DRY:              {n}
  SIMPLIFICATION:   {n}
  DOC_ACCURACY:     {n}
  DOC_COMPLETENESS: {n}
  DOC_MISSING:      {n}
  ...

--- DETAILED REMARKS ---

[{severity} | {category}] {file}:{line}
{note}

[{severity} | {category}] {file}:{line}
{note}
...
```

Print ALL remarks inline — there is no MR to post comments to, so the console output IS the review.

## Notes

- No GitLab interaction — this is a purely local review
- All findings are printed to console, not posted anywhere
- Sub-agents are intentionally isolated from orchestrator context to ensure objectivity
- The orchestrator MUST NOT interpret, summarize, or filter the changes before handing them to sub-agents
- Comments are in Russian, informal "ты" form, matching the team's review style
