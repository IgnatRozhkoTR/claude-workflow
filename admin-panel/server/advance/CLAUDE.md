# Advance

Phase gate logic — the most complex subsystem in the server.

## Architecture

Each workflow sub-phase is a `Phase` subclass (in `phases/`) that encapsulates its identity, validation, and advancement logic. The orchestrator (`orchestrator.py`) drives the phase lifecycle generically — no hardcoded phase strings.

## Packages

- `phases/` — Phase ABC and all concrete phase definitions
  - `preparation.py` — phases 0 through 1.4 (init, assessment, research, proving, impact, preparation review gate)
  - `planning.py` — phase 2.0 (plan validation)
  - `execution.py` — phases 3.N.0 through 3.N.4 (implementation, verification, fix review, commit approval gate, commit) — parameterized by execution item N
  - `finalization.py` — phases 4.0 through 5 (agentic review, address fixes, final approval gate, done)

- `orchestrator.py` — `perform_advance()`, `approve_gate()`, `reject_gate()`, `transition_phase()`. Uses Phase objects for all phase-specific decisions.

- `guards.py` — cross-cutting `AdvanceGuard` classes that apply across phase ranges. Guards self-select by phase, independent of advancers.

- `permissions.py` — tool permission enforcement during phases.

- `validators.py` — programmatic acceptance criteria validation.

## How to add a new phase

1. Create a Phase subclass in the appropriate file under `phases/`
2. Set `id`, `name`, implement `validate()` and `next_phase()`
3. For gates: set `is_user_gate = True`, `approve_target`, `reject_target`
4. Register it in the file's `PHASES` list (or via `get_execution_phase` for 3.N.K)
