# Isometric Dungeon — Interface Tests

Tests each module must pass **before it can be accepted** into the main branch.  
Every module can be developed independently as long as it fulfils the agreed interface contract.

---

## 1) `test_maze_contract.py` — Maze Domain Tests

These tests import **only** `maze.py`.  They verify the public types and the `Maze` class contract.

### 1.1 Type-level checks

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| M-T01     | `Direction` has 4 members              | `set(Direction)` == `{N, S, E, W}`                                        |
| M-T02     | `Direction.N.opposite` is `S`          | Verify each direction's `.opposite` property                              |
| M-T03     | `Direction` deltas are correct         | `N.dr == -1, N.dc == 0`, etc.                                            |
| M-T04     | `Position` is frozen                   | `Position(0,0)` can be used in a `set` and cannot be mutated              |
| M-T05     | `Position.moved()` works               | `Position(1,1).moved(Direction.N)` == `Position(0,1)`                     |
| M-T06     | `Position.to_dict()` round-trips       | `Position.from_dict(pos.to_dict()) == pos`                                |
| M-T07     | `CellKind` has 3 members               | `START, EXIT, NORMAL`                                                     |
| M-T08     | `CellSpec.is_passable()`               | Returns `False` for blocked directions, `True` otherwise                  |

### 1.2 `build_3x3_maze()` contract

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| M-301     | Maze dimensions                        | `width == 3`, `height == 3`                                               |
| M-302     | Start cell                             | `maze.start == Position(0,0)` and `cell.kind == START`                    |
| M-303     | Exit cell                              | `maze.exit == Position(2,2)` and `cell.kind == EXIT`                      |
| M-304     | All 9 cells exist                      | `len(maze.all_positions()) == 9`                                          |
| M-305     | At least 2 pillars placed              | Count cells where `pillar_type is not None` >= 2                          |
| M-306     | At least 1 pit                         | At least one cell with `has_pit == True`                                  |
| M-307     | Known wall: (0,1)→S is blocked         | `Direction.S in maze.cell(Position(0,1)).blocked`                         |
| M-308     | Walls are symmetric                    | If (0,1)→S blocked then (1,1)→N blocked                                  |
| M-309     | `available_moves` at start             | `maze.available_moves(Position(0,0))` == `{S, E}`                         |
| M-310     | `next_pos` into wall returns None      | `maze.next_pos(Position(0,1), Direction.S)` is `None`                     |
| M-311     | `next_pos` on valid move               | `maze.next_pos(Position(0,0), Direction.E)` == `Position(0,1)`            |
| M-312     | Exit reachable                         | BFS from start reaches exit (path exists)                                 |
| M-313     | All pillars reachable                  | BFS from start reaches every pillar cell                                  |

### 1.3 `build_square_maze(size, seed)` contract

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| M-S01     | Dimensions are correct                 | `width == size`, `height == size`                                         |
| M-S02     | Start at (0,0)                         | `maze.start == Position(0,0)`                                             |
| M-S03     | Exit at (size-1, size-1)               | `maze.exit == Position(size-1, size-1)`                                   |
| M-S04     | Deterministic                          | Same `(size, seed)` → identical maze                                      |
| M-S05     | Different seed → different maze        | Two different seeds produce different wall patterns                        |
| M-S06     | Every cell reachable                   | BFS from start visits all `size*size` cells                               |
| M-S07     | At least 4 pillars placed              | Count pillars >= 4 (for `size >= 5`)                                      |

### 1.4 Constraint enforcement (no `print`, no imports)

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| M-C01     | `maze.py` does not import `db`         | `"import db"` not in source text                                          |
| M-C02     | `maze.py` does not import `main`       | `"import main"` not in source text                                        |
| M-C03     | `maze.py` does not call `print()`      | `"print("` not in source text (outside comments/strings)                  |

---

## 2) `test_repo_contract.py` — DB Persistence Tests

These tests import **only** `db.py`.  They use a temp file for isolation.

### 2.1 Player operations

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| D-P01     | Create player                          | `get_or_create_player("Hero")` returns `PlayerRecord` with `.handle == "Hero"` |
| D-P02     | Idempotent create                      | Calling twice with same handle returns same `.id`                          |
| D-P03     | Get by ID                              | `get_player(id)` returns matching record                                   |
| D-P04     | Get missing player                     | `get_player("nonexistent")` returns `None`                                 |

### 2.2 Game operations

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| D-G01     | Create game                            | `create_game(...)` returns `GameRecord` with `status == "in_progress"`     |
| D-G02     | Get game                               | `get_game(id)` returns matching record                                     |
| D-G03     | Save game updates state                | After `save_game(id, new_state)`, `get_game(id).state` == `new_state`      |
| D-G04     | Save game updates status               | `save_game(id, state, "completed")` → `status == "completed"`             |
| D-G05     | Save game updates timestamp            | `updated_at` changes after `save_game`                                     |
| D-G06     | Get missing game                       | `get_game("nonexistent")` returns `None`                                   |
| D-G07     | State is opaque dict                   | Stores `{"pos": {"row": 1, "col": 2}, "custom_key": [1,2,3]}` without error |

### 2.3 Score operations

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| D-S01     | Record score                           | `record_score(...)` returns `ScoreRecord` with matching fields            |
| D-S02     | Top scores returns list                | `top_scores()` returns `list[ScoreRecord]`                                 |
| D-S03     | Top scores ordered                     | Lower `move_count` first                                                   |
| D-S04     | Top scores filter by maze_id           | `top_scores(maze_id="x")` only returns scores for maze `"x"`              |
| D-S05     | Top scores respects limit              | `top_scores(limit=2)` returns at most 2                                    |

### 2.4 Persistence

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| D-IO01    | Data survives reload                   | Create repo, add data, create new repo from same path → data present       |
| D-IO02    | Schema version present                 | JSON file contains `"schema_version": 1`                                   |
| D-IO03    | JSON is valid                          | File content parses as valid JSON                                          |

### 2.5 Constraint enforcement

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| D-C01     | `db.py` does not import `maze`         | `"import maze"` not in source text                                         |
| D-C02     | `db.py` does not import `main`         | `"import main"` not in source text                                         |

---

## 3) `test_engine_integration.py` — Full Integration Tests

These tests import all three modules.  They test the engine wiring end-to-end.

### 3.1 Engine initialisation

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| E-I01     | Engine creates with maze + repo        | `GameEngine(maze, repo, pid, gid)` does not raise                          |
| E-I02     | Initial view has start position        | `engine.view().pos == {"row": 0, "col": 0}`                               |
| E-I03     | Initial view is not complete           | `engine.view().is_complete == False`                                       |
| E-I04     | Initial view is not dead               | `engine.view().is_dead == False`                                           |

### 3.2 Movement

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| E-M01     | Valid move changes position            | Move `E` from (0,0) → view shows (0,1)                                    |
| E-M02     | Invalid move blocked by wall           | Move into wall → position unchanged, message says "wall"                   |
| E-M03     | Move out of bounds blocked             | Move `N` from (0,0) → position unchanged                                  |
| E-M04     | Move count increments                  | After 3 valid moves, `view().move_count == 3`                              |

### 3.3 Item interactions

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| E-IT01    | Pillar pickup                          | Moving onto pillar cell adds to `pillars_found`                            |
| E-IT02    | Healing potion pickup                  | Moving onto potion cell increments `healing_potions`                       |
| E-IT03    | Pit damage                             | Moving onto pit cell reduces `hp`                                          |
| E-IT04    | Heal command uses potion               | After picking up potion, `heal` restores HP and decrements count           |

### 3.4 Win / lose conditions

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| E-W01     | Exit locked without pillars            | Reaching exit without all pillars → not complete, message says "locked"    |
| E-W02     | Exit unlocked with all pillars         | Reaching exit with all pillars → `is_complete == True`                     |
| E-W03     | Death from pit damage                  | If HP reaches 0 → `is_dead == True`                                       |
| E-W04     | Score recorded on win                  | After winning, `repo.top_scores()` has an entry                            |

### 3.5 Persistence round-trip

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| E-P01     | Save command persists                  | After `save`, `repo.get_game(gid).state["move_count"]` matches engine     |
| E-P02     | Position serialised correctly          | `state["pos"]` == `{"row": r, "col": c}`                                  |
| E-P03     | Visited list serialised                | `state["visited"]` is a list of `{"row":…, "col":…}` dicts                |
| E-P04     | Pillars serialised as strings          | `state["pillars_found"]` is `list[str]`                                    |

### 3.6 Boundary enforcement

| Test ID   | Test Name                              | Assertion                                                                 |
|-----------|----------------------------------------|---------------------------------------------------------------------------|
| E-B01     | No maze types in DB state              | `state` dict contains no `Position` or `Enum` objects — only JSON primitives |
| E-B02     | `main.py` imports maze and db          | Source contains `import maze` / `from maze import` and `import db` / `from db import` |
| E-B03     | Engine never calls print               | `GameEngine` source does not contain `print(`                              |

---

## 4) Summary: Acceptance Criteria Per Module

| Module     | Must pass                       | Before merging? |
|-----------|----------------------------------|-----------------|
| `maze.py`  | All `M-*` tests                 | Yes             |
| `db.py`    | All `D-*` tests                 | Yes             |
| `main.py`  | All `E-*` tests                 | Yes             |

Each programmer can work on their module in isolation.  As long as the tests pass, the modules will integrate cleanly at merge time.
