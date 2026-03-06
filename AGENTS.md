# AGENTS — Contribution Rules (Human-Readable, Agent-Focused)

This file tells coding agents (and humans) how to contribute safely to the quiz maze walking skeleton without breaking shared contracts or other developers’ work.

If there is any conflict between documents:
1. `interfaces.md` (contracts) wins
2. `RUNBOOK.md` (workflow + merge gate) wins
3. this file provides operational guidance

## Golden Rules (Non-Negotiable)

- **No cross-imports**
  - `maze.py` must not import `db.py` or `main.py`
  - `db.py` must not import `maze.py` or `main.py`
  - `main.py` is the only integration point

- **DB stores JSON-safe primitives only**
  - positions persist as `{"row": int, "col": int}` (not `Position`)
  - timestamps persist as ISO-8601 UTC strings

- **Engine is UI-agnostic**
  - core logic must not call `input()` or `print()`
  - CLI/PyQt adapters handle input/output

- **Shared integration tests are the contract**
  - do not add “test-only” behavior that violates `interfaces.md`
  - if you change a contract intentionally, update the contract docs and tests together

## GitHub PR Workflow (No CI Yet)

We use GitHub PRs. No automated CI runner is configured yet.

PR author responsibilities:
- run tests locally
- paste test results and exact command(s) used in the PR description
- keep PRs small and focused (one concern per PR)
- treat this manual test gate as required policy for PRs to `master` until CI is added

Recommended branch naming:
- `feat/<area>-<short-description>`
- `fix/<area>-<short-description>`
- `docs/<short-description>`
- `test/<short-description>`
- `refactor/<area>-<short-description>`

Areas: `maze`, `db`, `engine`, `cli`, `puzzles`, `docs`, `tests`

## PR Checklist (Copy/Paste)

- [ ] Scope: one module/concern (maze OR db OR engine/cli OR docs/tests)
- [ ] Tests run locally:
  - [ ] `python -m pytest -q`
- [ ] PR includes test evidence:
  - [ ] command(s) run
  - [ ] final pass/fail summary
  - [ ] note on any skipped tests and why
- [ ] Shared P0 integration tests pass (see `RUNBOOK.md`)
- [ ] No contract drift:
  - [ ] if contracts changed, updated `interfaces.md`
  - [ ] if shared tests changed, updated `integration-tests-spec.md`
  - [ ] if workflow/gates changed, updated `RUNBOOK.md`
- [ ] Notes on playability impact (does `main.py` remain playable?)

## How to Add Features Safely (Without Breaking Others)

Prefer additive changes:
- add new commands/verbs rather than changing existing semantics
- add new optional fields in persisted `state` and tolerate missing keys on load
- add new puzzles via new `puzzle_id`s; do not rename/remove existing IDs without a migration strategy

Keep determinism for tests:
- any randomness must be seedable (or disabled in tests)
- time must be injectable/controllable in the engine

## Module-Specific Guidance (Minimum Expectations)

### `maze.py`
- deterministic `build_minimal_3x3_maze()`
- movement rules are purely topology
- gates are *reported* via `gate_id_for`, not enforced by maze logic

### `db.py`
- repository methods match `interfaces.md`
- persistence is JSON-only for now (SQLite later) but behavior must be portable
- score ordering must match shared tests (walking skeleton rule: lowest `elapsed_seconds`, then lowest `moves`)

### `main.py`
- engine returns stable `GameView`
- CLI is an adapter that translates user input to `Command` and renders `GameView`
- unknown commands are safe (error/help message; no state corruption)

