# Isometric Dungeon — RUNBOOK

Operational guide for the walking skeleton.  
Defines dependency rules, how to run the game, how to run tests, and what "done" means.

---

## 1) Project Structure

```
walking_skeleton/
├── maze.py                      # Domain logic — pure Python
├── db.py                        # Persistence — JSON I/O
├── main.py                      # Engine — the wiring + CLI
├── test_maze_contract.py        # Tests for maze.py
├── test_repo_contract.py        # Tests for db.py
├── test_engine_integration.py   # Integration tests
├── game_data.json               # (auto-created at runtime)
└── docs/
    ├── interfaces.md            # Interface contracts
    ├── interface-tests.md       # Test specifications
    └── RUNBOOK.md               # This file
```

---

## 2) Dependency Rules

These rules are **non-negotiable**.  Violating them breaks module independence.

| Rule | Constraint |
|------|-----------|
| **R1** | `maze.py` imports **nothing** from `db` or `main` |
| **R2** | `maze.py` never calls `print()` |
| **R3** | `db.py` imports **nothing** from `maze` or `main` |
| **R4** | `db.py` stores only JSON-serialisable primitives (`str`, `int`, `float`, `bool`, `None`, `list`, `dict`) |
| **R5** | `main.py` is the **only** module that imports `maze` and `db` |
| **R6** | `main.py` is the **only** module that calls `print()` or `input()` |
| **R7** | Position objects are converted to `{"row": int, "col": int}` dicts **before** crossing into `db.py` |
| **R8** | Enums are stored as their `.name` or `.value` string in the DB |

### Why these rules matter

- **R1–R3**: Each module can be developed, tested, and replaced independently.
- **R4, R7, R8**: The DB layer can switch from JSON to SQLite without touching maze.py.
- **R5**: Single integration point — merge conflicts are localised to main.py.
- **R6**: The UI can change (CLI → PyGame → PyQt) without modifying domain or persistence logic.

---

## 3) How to Run

### Play the game (CLI)

```bash
cd walking_skeleton
python main.py
```

Commands: `n`, `s`, `e`, `w`, `look`, `map`, `heal`, `save`, `quit`

### Run all tests

```bash
cd walking_skeleton
python -m pytest test_maze_contract.py test_repo_contract.py test_engine_integration.py -v
```

Or run individual suites:

```bash
python -m pytest test_maze_contract.py -v       # maze only
python -m pytest test_repo_contract.py -v        # db only
python -m pytest test_engine_integration.py -v   # full integration
```

### Run without pytest (stdlib unittest)

```bash
python -m unittest test_maze_contract -v
python -m unittest test_repo_contract -v
python -m unittest test_engine_integration -v
```

---

## 4) P0 (Critical) Tests — Definition of Done

The project is "done" when **all** P0 tests pass.  These are the non-negotiable minimum.

### P0 — Maze (`maze.py`)

| ID     | Test                                | Why it's critical                              |
|--------|-------------------------------------|------------------------------------------------|
| M-302  | Start cell at (0,0)                | Game can't begin without a valid start         |
| M-303  | Exit cell at (2,2)                 | Game can't be won without a valid exit         |
| M-304  | All 9 cells exist                  | Maze must be structurally complete             |
| M-309  | Available moves at start           | Proves wall/collision logic works              |
| M-312  | Exit is reachable from start       | Game must be winnable                          |
| M-313  | All pillars reachable              | All pillars must be collectible                |
| M-C01  | No import of db                    | Boundary rule R1                               |
| M-C03  | No print() calls                   | Boundary rule R2                               |

### P0 — Database (`db.py`)

| ID      | Test                               | Why it's critical                              |
|---------|-------------------------------------|------------------------------------------------|
| D-P01   | Create player                      | Can't play without a player record             |
| D-G01   | Create game                        | Can't track state without a game record        |
| D-G03   | Save game updates state            | Save/load is core persistence functionality    |
| D-IO01  | Data survives reload               | Persistence must actually persist              |
| D-C01   | No import of maze                  | Boundary rule R3                               |

### P0 — Engine Integration (`main.py`)

| ID     | Test                                | Why it's critical                              |
|--------|-------------------------------------|------------------------------------------------|
| E-I01  | Engine creates without error        | Basic wiring must work                         |
| E-M01  | Valid move changes position         | Movement is the core game mechanic             |
| E-M02  | Wall blocks movement                | Collision must work                            |
| E-IT01 | Pillar pickup works                 | Must be able to collect pillars to win         |
| E-W02  | Win with all pillars at exit        | Win condition is the game's objective          |
| E-P01  | Save persists state                 | Save/load round-trip must work                 |
| E-B01  | No maze types leak into DB state    | Boundary enforcement is architectural          |

### Totals

| Module   | P0 tests | Total tests |
|----------|----------|-------------|
| maze.py  | 8        | ~20         |
| db.py    | 5        | ~14         |
| main.py  | 7        | ~17         |
| **Total**| **20**   | **~51**     |

---

## 5) Development Workflow

### For each programmer:

1. **Pull** the walking skeleton branch
2. **Read** `docs/interfaces.md` — understand the contract
3. **Read** `docs/interface-tests.md` — understand what tests your module needs to pass
4. **Write / modify** your assigned module (`maze.py`, `db.py`, or `main.py`)
5. **Run** your module's test suite — make all tests pass
6. **Push** to your feature branch
7. **PR** against the skeleton branch — CI runs integration tests

### Branch strategy

```
main
 └── feature/walking-skeleton          ← this branch
      ├── feature/maze-impl            ← maze.py developer
      ├── feature/db-impl              ← db.py developer
      └── feature/engine-impl          ← main.py developer
```

### Integration checklist

Before merging any module branch:

- [ ] All P0 tests for that module pass
- [ ] No forbidden imports (checked by constraint tests)
- [ ] No `print()` in maze.py or db.py
- [ ] Full integration suite passes when combined with the other modules

---

## 6) Known Limitations (Walking Skeleton)

These are intentional scopes cuts for the skeleton:

| Limitation                         | Resolution planned for            |
|-----------------------------------|-----------------------------------|
| Only 2 pillars (not 4)            | Expand when maze grows beyond 3×3 |
| No vision potion mechanic         | Wire up in engine iteration 2     |
| No isometric rendering            | PyGame frontend connects to same engine |
| JSON-only persistence             | SQLite backend via `open_repo()`  |
| No puzzle / question gates        | Add PuzzleRegistry + question bank |
| No save-game resume               | Load existing `GameRecord` at startup |
| No leaderboard UI                 | `top_scores()` is ready; needs display |

---

## 7) Troubleshooting

| Problem                        | Solution                                            |
|-------------------------------|-----------------------------------------------------|
| `ModuleNotFoundError: maze`    | Run from within the `walking_skeleton/` directory   |
| `FileNotFoundError: game_data.json` | Normal on first run — file is auto-created    |
| Tests fail with `ImportError`  | Ensure `pytest` is installed: `pip install pytest`  |
| JSON file corrupted            | Delete `game_data.json` and restart                 |
| `KeyError` in db.py           | Ensure `game_id` exists before calling `save_game`  |
