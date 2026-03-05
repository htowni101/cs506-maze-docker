# RUNBOOK — Quiz Maze Walking Skeleton

This runbook is the day-to-day operational guide for developing the quiz maze walking skeleton in parallel, while keeping a playable mini-game and preserving clean module boundaries.

Source-of-truth docs:
- `interfaces.md` (module contracts)
- `integration-tests-spec.md` (detailed test descriptions)
- `planning.md` (ownership + merge order)
- `customization-design-plan.md` (theme + growth roadmap)
- `AGENTS.md` (agent-focused contribution rules)

## Purpose (and Non-Goals)

**Purpose**: enable multiple developers/agents to implement `maze.py`, `db.py`, and `main.py` independently, with shared integration tests acting as the executable contract.
**Non-goals for this phase**: PyQt UI tests, randomized maze generation, performance/load testing, multiplayer/networking.

## Module Ownership and Boundaries

Hard dependency rule (do not violate):
- `maze.py` imports nothing from `db.py` or `main.py`
- `db.py` imports nothing from `maze.py` or `main.py`
- `main.py` is the only integration point

Responsibilities:
- **`maze.py` (Maze Owner)**: deterministic maze factory + topology/movement API + gate/puzzle hooks (no puzzle logic).
- **`db.py` (DB Owner)**: JSON-backed repository implementing the repo interface (mock ORM boundary) storing JSON-safe primitives only.
- **`main.py` (Engine/CLI Owner)**: UI-agnostic engine + CLI adapter; uses `Maze` + repository + puzzle registry.

## Workflow and Branching

Baseline branch:
- `planning` is the baseline for contracts and planning docs.

Feature branches (recommended standard):
- `feat/<area>-<short-description>` (new behavior)
- `fix/<area>-<short-description>` (bug fixes)
- `docs/<short-description>` (docs-only changes)
- `test/<short-description>` (tests-only changes)
- `refactor/<area>-<short-description>` (refactors without behavior change)

Areas (pick one):
- `maze`, `db`, `engine`, `cli`, `puzzles`, `docs`, `tests`

Examples:
- `feat/maze-minimal-3x3`
- `feat/db-json-repo`
- `feat/engine-command-parser`
- `docs/runbook-updates`

Merge order:
1. Maze contract work can merge once Maze P0 tests pass.
2. DB contract work can merge once Repo P0 tests pass.
3. Engine/CLI merges once Maze+DB contracts are stable and Engine P0 tests pass.

## Merge Gate (Must Pass)

Every PR must pass:
- **Module unit tests** for the changed component(s)
- **Shared integration tests** (see backlog below)
- **Interface compatibility**: no contract drift vs `interfaces.md` unless explicitly updated (and reviewed)

No CI runner is configured yet. This means the PR author is responsible for running tests locally and reporting results in the PR description.
This manual test gate is part of the current `master` baseline and should not be removed by feature branches.

Recommended local commands (to include in PR):
- `python -m pytest -q`
- (optional during development) `python -m pytest -q tests/test_maze_contract.py`

Required PR evidence (until CI exists):
- Paste command(s) run and the final pass/fail summary.
- Confirm whether all P0 tests passed.
- If any test was skipped, explain why and link follow-up work.

## Shared Integration Test Backlog (Priority Ordered)

Test file targets:
- `tests/test_maze_contract.py`
- `tests/test_repo_contract.py`
- `tests/test_engine_integration.py`

### P0 — Critical Path (must pass before any feature merges)

Maze contract (`tests/test_maze_contract.py`):
- `test_minimal_maze_start_exit_in_bounds`
- `test_available_moves_match_next_pos`
- `test_exit_reachable_from_start_via_public_api`
- `test_gate_and_puzzle_hooks_are_stable`

Repository contract (`tests/test_repo_contract.py`):
- `test_json_schema_root_keys_exist`
- `test_get_or_create_player_is_idempotent`
- `test_create_and_get_game_round_trip`
- `test_save_game_updates_state_and_status`
- `test_record_score_and_top_scores_ordering`

Engine end-to-end (`tests/test_engine_integration.py`):
- `test_new_game_view_has_valid_position_and_moves`
- `test_player_can_progress_after_solving_required_puzzle`
- `test_reaching_exit_completes_game_and_records_score`

Definition of “P0 done”:
- P0 tests pass on every branch, without test-only shortcuts that violate `interfaces.md`.
- Running `main.py` provides a playable 3x3 mini-game (move, solve at least one gate puzzle, reach exit, persist score).

### P1 — Contract Hardening (merge when ready; required before expanding scope)

Engine robustness (`tests/test_engine_integration.py`):
- `test_save_command_persists_progress_mid_run`
- `test_invalid_command_does_not_corrupt_state`

Repository semantics (extend `tests/test_repo_contract.py` as needed):
- Confirm `updated_at` monotonicity for repeated `save_game` calls
- Validate score ordering ties (secondary key: lowest `moves`)

### P2 — Expansion-Ready (protect future SQLite + PyQt work)

DB portability:
- Re-run the same repo contract suite against a future `SqliteGameRepository` implementation (no behavior drift).

Engine UI-agnostic guarantees:
- Ensure the engine returns a stable `GameView` that can render in both CLI and PyQt without accessing internal engine state.

## Per-Module Implementation Checklists (Tied to Shared Tests)

Each checklist item must be satisfied *and* the referenced tests must pass.

### Maze Owner Checklist (`maze.py`)

- [ ] Implement `build_minimal_3x3_maze()` deterministic factory.
  - **Verify**: `tests/test_maze_contract.py::test_minimal_maze_start_exit_in_bounds`
- [ ] Implement movement topology methods: `in_bounds`, `available_moves`, `next_pos`.
  - **Verify**: `tests/test_maze_contract.py::test_available_moves_match_next_pos`
- [ ] Ensure exit is reachable via public API (no hidden shortcuts).
  - **Verify**: `tests/test_maze_contract.py::test_exit_reachable_from_start_via_public_api`
- [ ] Provide stable hooks: `puzzle_id_at(pos)` and `gate_id_for(pos, dir)`.
  - **Verify**: `tests/test_maze_contract.py::test_gate_and_puzzle_hooks_are_stable`

Done when:
- All Maze P0 tests pass and the module has no imports of `db.py`/`main.py`.

### DB Owner Checklist (`db.py`)

- [ ] Implement JSON schema bootstrap (`schema_version`, `players`, `games`, `scores`).
  - **Verify**: `tests/test_repo_contract.py::test_json_schema_root_keys_exist`
- [ ] Implement `get_or_create_player(handle)` idempotently.
  - **Verify**: `tests/test_repo_contract.py::test_get_or_create_player_is_idempotent`
- [ ] Implement game lifecycle: `create_game`, `get_game`, `save_game`.
  - **Verify**: `tests/test_repo_contract.py::test_create_and_get_game_round_trip`, `tests/test_repo_contract.py::test_save_game_updates_state_and_status`
- [ ] Implement scoring: `record_score`, `top_scores` ordered by lowest `elapsed_seconds`, then lowest `moves`.
  - **Verify**: `tests/test_repo_contract.py::test_record_score_and_top_scores_ordering`

Done when:
- All Repo P0 tests pass using only JSON-safe primitives, and `db.py` does not import `maze.py`/`main.py`.

### Engine/CLI Owner Checklist (`main.py`)

- [ ] Create an engine that is UI-agnostic (no direct I/O in core logic) and returns `GameView`.
  - **Verify**: `tests/test_engine_integration.py::test_new_game_view_has_valid_position_and_moves`
- [ ] Implement puzzle gating flow: pending puzzle appears, `answer` resolves, movement retries succeed.
  - **Verify**: `tests/test_engine_integration.py::test_player_can_progress_after_solving_required_puzzle`
- [ ] Implement completion flow: reaching exit marks game completed and records score.
  - **Verify**: `tests/test_engine_integration.py::test_reaching_exit_completes_game_and_records_score`
- [ ] Add `save` command persistence and invalid command safety.
  - **Verify**: P1 engine tests (`test_save_command_persists_progress_mid_run`, `test_invalid_command_does_not_corrupt_state`)

Done when:
- All Engine P0 tests pass and `main.py` runs a playable mini-game via CLI.

## Execution Sequence (Recommended)

1) **Maze Owner** implements Maze P0 until `tests/test_maze_contract.py` passes.
2) **DB Owner** implements Repo P0 until `tests/test_repo_contract.py` passes.
3) **Engine/CLI Owner** implements Engine P0 end-to-end until `tests/test_engine_integration.py` passes.
4) Implement P1 hardening (save + invalid command), then start content expansion (more puzzles/mazes).

