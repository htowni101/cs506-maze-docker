# Isometric Dungeon — Module Interfaces (Walking Skeleton)

This document defines the **stable contracts** between the 3 modules:

- `maze.py` — domain / world model (pure Python)
- `db.py` — persistence boundary (JSON-backed mock ORM for now)
- `main.py` — game engine + UI wiring (CLI now, isometric PyGame later)

The goal: each module can be **developed and tested independently**.

---

## 1) Dependency Rules

| Module   | May import          | May NOT import        |
|----------|--------------------|-----------------------|
| `maze.py`| stdlib only         | `db`, `main`          |
| `db.py`  | stdlib only         | `maze`, `main`        |
| `main.py`| `maze`, `db`        | *(nothing restricted)*|

- `maze.py` cannot call `print()`.  It outputs **data**, not text.
- `db.py` stores **only JSON-serialisable primitives**.  
  Any `maze.Position` objects must be converted to/from `{"row": int, "col": int}` **at the boundary** (inside `main.py`).
- `main.py` is the **only** module that calls `print()` or `input()`.

---

## 2) Shared Serialisation Rules (DB Boundary)

All persisted state must be JSON-safe:

- `str | int | float | bool | None`
- `list[...]` of JSON-safe values
- `dict[str, ...]` of JSON-safe values

**Position** is converted at the boundary:

```python
# main.py converts BEFORE sending to db:
pos_dict = {"row": pos.row, "col": pos.col}

# main.py converts AFTER reading from db:
pos = Position(row=d["row"], col=d["col"])
```

**Enums** (Direction, CellKind) are stored as their `.value` or `.name` string.

**Timestamps**: ISO-8601 UTC strings, e.g. `"2026-02-25T14:30:00Z"`.

---

## 3) `maze.py` — Domain Contract

### 3.1 Public Types

#### `Direction` (Enum)

| Value | Delta `(dr, dc)` |
|-------|-------------------|
| `N`   | `(-1, 0)`         |
| `S`   | `(1, 0)`          |
| `E`   | `(0, 1)`          |
| `W`   | `(0, -1)`         |

Properties: `.dr`, `.dc`, `.opposite`.

#### `Position` (frozen dataclass)

```python
@dataclass(frozen=True)
class Position:
    row: int
    col: int

    def moved(direction: Direction) -> Position
    def to_dict() -> dict            # {"row": int, "col": int}

    @classmethod
    def from_dict(d: dict) -> Position
```

#### `CellKind` (Enum)

Values: `START`, `EXIT`, `NORMAL`.

#### `CellSpec` (dataclass)

```python
@dataclass
class CellSpec:
    pos: Position
    kind: CellKind = NORMAL
    blocked: set[Direction]          # directions you CANNOT walk
    pillar_type: str | None          # e.g. "pillar_a", "pillar_e"
    has_pit: bool
    has_healing_potion: bool
    has_vision_potion: bool

    def is_passable(direction: Direction) -> bool
```

### 3.2 `Maze` Class — What `main.py` Relies On

```python
class Maze:
    # Identity
    maze_id: str                     # e.g. "maze-3x3-v1"
    maze_version: str                # e.g. "1.0"
    width: int
    height: int
    start: Position
    exit: Position

    # Topology queries
    def in_bounds(pos: Position) -> bool
    def cell(pos: Position) -> CellSpec
    def available_moves(pos: Position) -> set[Direction]
    def next_pos(pos: Position, direction: Direction) -> Position | None
    def pillar_type_at(pos: Position) -> str | None
    def all_positions() -> list[Position]
    def all_cells() -> list[CellSpec]
```

### 3.3 Factories

| Factory                              | Description                                           |
|--------------------------------------|-------------------------------------------------------|
| `build_3x3_maze() -> Maze`          | Deterministic hand-authored 3×3 layout with 2 pillars, 1 pit, 1 potion |
| `build_square_maze(size, seed) -> Maze` | Seeded procedural N×N maze (recursive backtracker), 4 pillars |

#### 3×3 Walking Skeleton Layout

```
(0,0) START ──► (0,1)       ──► (0,2) PILLAR_A
  │               ║ wall            │
  ▼               ║                 ▼
(1,0) PIT   ──► (1,1)       ──► (1,2) heal potion
  │               │
  ▼               ▼
(2,0)       ║  (2,1) PILLAR_E  ──► (2,2) EXIT
            ║ wall
```

Walls:
- `(0,1)↔(1,1)` — blocks the central shortcut
- `(2,0)↔(2,1)` — forces the player to take a longer path

Minimum path: `(0,0)→(1,0)→(1,1)→(2,1)→(2,2)` — but that skips `pillar_a`.
Collecting both pillars requires visiting `(0,2)` and `(2,1)`.

### 3.4 Fog of War

Fog-of-war is handled by the **engine/CLI renderer** in `main.py`, not by `maze.py`.  
The maze stays purely topological.  The renderer receives a `visited: set[Position]` and hides unvisited cells.

---

## 4) `db.py` — Persistence Contract (JSON I/O)

### 4.1 Record DTOs

#### `PlayerRecord`

| Field        | Type  |
|-------------|-------|
| `id`         | `str` (UUID) |
| `handle`     | `str` |
| `created_at` | `str` (ISO-8601) |

#### `GameRecord`

| Field          | Type  |
|---------------|-------|
| `id`           | `str` (UUID) |
| `player_id`    | `str` |
| `maze_id`      | `str` |
| `maze_version` | `str` |
| `state`        | `dict[str, Any]` (opaque to db) |
| `status`       | `str` — `"in_progress"` or `"completed"` |
| `created_at`   | `str` (ISO-8601) |
| `updated_at`   | `str` (ISO-8601) |

#### `ScoreRecord`

| Field          | Type  |
|---------------|-------|
| `id`           | `str` (UUID) |
| `player_id`    | `str` |
| `game_id`      | `str` |
| `maze_id`      | `str` |
| `maze_version` | `str` |
| `metrics`      | `dict[str, Any]` |
| `created_at`   | `str` (ISO-8601) |

### 4.2 Repository Interface (minimum)

`main.py` depends on an object providing these methods:

```python
class GameRepository:
    # Player ops
    def get_player(player_id: str) -> PlayerRecord | None
    def get_or_create_player(handle: str) -> PlayerRecord

    # Game ops
    def create_game(player_id, maze_id, maze_version, initial_state: dict) -> GameRecord
    def get_game(game_id: str) -> GameRecord | None
    def save_game(game_id: str, state: dict, status: str) -> GameRecord

    # Score ops
    def record_score(player_id, game_id, maze_id, maze_version, metrics: dict) -> ScoreRecord
    def top_scores(maze_id: str | None, limit: int) -> list[ScoreRecord]
```

**Key rule**: `state` is **opaque** to the DB layer.  It stores whatever dict `main.py` hands it without inspecting or importing `maze` types.

### 4.3 JSON File Shape

```json
{
  "schema_version": 1,
  "players": { "<player_id>": { "id": "...", "handle": "...", "created_at": "..." } },
  "games":   { "<game_id>":   { "id": "...", "player_id": "...", "state": {...}, ... } },
  "scores":  { "<score_id>":  { "id": "...", "metrics": {...}, ... } }
}
```

### 4.4 How Position Crosses the DB Boundary

```
                main.py (boundary)
maze.Position ──────────────────────► {"row": int, "col": int}
              _pos_to_dict()                     │
                                                 ▼
                                         db.save_game(state)
                                                 │
                                                 ▼
                                          JSON file on disk

              _dict_to_pos()                     │
maze.Position ◄──────────────────────  db.get_game(id).state
```

`main.py` owns the conversion functions:
- `_pos_to_dict(pos: Position) -> dict`
- `_dict_to_pos(d: dict) -> Position`

`db.py` never touches `Position`.  It only sees `dict`.

### 4.5 Future: SQLite Backend

`open_repo(path)` checks the file extension:
- `.json` → `JsonGameRepository`
- `.db` → `SqliteGameRepository` *(not yet implemented)*

---

## 5) `main.py` — Engine + CLI Wiring

### 5.1 Engine State (persisted via DB as JSON dict)

```python
@dataclass
class EngineState:
    pos: Position
    move_count: int
    hp: int
    max_hp: int
    healing_potions: int
    vision_potions: int
    pillars_found: list[str]
    visited: set[Position]
    is_complete: bool
    is_dead: bool
```

Persisted as:

```json
{
  "pos": {"row": 0, "col": 0},
  "move_count": 5,
  "hp": 85,
  "max_hp": 100,
  "healing_potions": 1,
  "vision_potions": 0,
  "pillars_found": ["pillar_a"],
  "visited": [{"row": 0, "col": 0}, {"row": 0, "col": 1}],
  "is_complete": false,
  "is_dead": false
}
```

### 5.2 Engine Contract (UI-agnostic)

```python
class GameEngine:
    def __init__(maze: Maze, repo: GameRepository, player_id: str, game_id: str, state: EngineState | None)
    def view() -> GameView
    def handle(cmd: Command) -> GameOutput
```

#### `Command`
```python
@dataclass
class Command:
    verb: str
    args: list[str]
```

#### `GameView` (what the UI renders)
```python
@dataclass
class GameView:
    pos: dict                       # {"row": int, "col": int}
    cell_kind: str                  # "START" | "EXIT" | "NORMAL"
    available_moves: list[str]      # ["N", "E"]
    hp: int
    max_hp: int
    healing_potions: int
    vision_potions: int
    pillars_found: list[str]
    move_count: int
    is_complete: bool
    is_dead: bool
    map_text: str | None            # pre-rendered ASCII fog-of-war map
```

#### `GameOutput`
```python
@dataclass
class GameOutput:
    view: GameView
    messages: list[str]
```

### 5.3 CLI Command Grammar (Walking Skeleton)

| Command            | Action                             |
|-------------------|------------------------------------|
| `n` / `s` / `e` / `w` | Move in that direction         |
| `go <direction>`  | Alias for movement                  |
| `look`            | Describe current cell & exits       |
| `map`             | Show ASCII fog-of-war map           |
| `heal` / `h`      | Use a healing potion               |
| `save`            | Persist game state to JSON          |
| `quit` / `q`      | Save and exit                      |

### 5.4 Map Rendering (fog of war)

```
  0   1   2
0  @  |###|###
1 ###|###|###
2 ###|###|###
```

- `@` = player position
- ` S ` = start (visited)
- ` X ` = exit (visited)
- ` P ` = pillar (visited)
- ` O ` = pit (visited)
- ` . ` = normal cell (visited)
- `###` = unvisited / fog

---

## 6) Versioning & Compatibility

| Key              | Stored in | Purpose                               |
|-----------------|-----------|---------------------------------------|
| `maze_id`        | DB        | Identifies which maze layout was used |
| `maze_version`   | DB        | Tracks maze layout changes            |
| `schema_version` | JSON file | DB schema version (currently `1`)     |

If `schema_version` changes → provide a migration path.  For the walking skeleton, keep it at `1`.
