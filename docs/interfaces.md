# Isometric Dungeon — Module Interfaces (MVP Refactor)

This document defines the stable contracts between the 3 modules:

- **maze.py** — domain / world model (pure Python)
- **db.py** — persistence boundary (SQLModel + SQLite ORM)
- **main.py** — game engine + UI wiring (CLI now, isometric PyGame later)

The goal: each module can be developed and tested independently.

---
## 0.5) Theme Vocabulary (MVP Requirement)

The underlying mechanics remain a Quiz Maze, but domain language must reflect the team theme.

Define and use these terms consistently across DB seed data and CLI text (MVP defaults):

- Location/Room term: `Room`
- Blocker/Door term: `Blocker`
- Question/Challenge term: `Challenge`
- Map term: `Map`
- DB seed tag: `mvp_default`

## 1) Dependency Rules

| Module    | May import                          | May NOT import |
| --------- | ------------                        | -------------- |
| maze.py   | stdlib only                         | db, main       |
| db.py     | stdlib + sqlmodel (+ sqlalchemy)    | maze, main     |
| main.py   | maze, db     | (nothing restricted) |

- **maze.py** cannot call `print()`. It outputs data, not text.
- **db.py** persists records using SQLModel + SQLite. The *engine state dict* remains JSON-safe and is stored opaquely (db does not inspect it). Any `maze.Position` objects must still be converted to/from `{"row": int, "col": int}` at the boundary (inside main.py).
- **main.py** is the only module that calls `print()` or `input()`.

---

## 2) Shared Serialisation Rules (DB Boundary)

All *engine state crossing the DB boundary* must be JSON-safe:

- `str` | `int` | `float` | `bool` | `None`
- `list[...]` of JSON-safe values
- `dict[str, ...]` of JSON-safe values

**Position** is converted at the boundary:

```python
# main.py converts BEFORE sending to db:
pos_dict = {"row": pos.row, "col": pos.col}

# main.py converts AFTER reading from db:
pos = Position(row=d["row"], col=d["col"])
```

**Enums** (`Direction`, `CellKind`) are stored as their `.value` or `.name` string.

**Timestamps:** ISO-8601 UTC strings, e.g. `"2026-02-25T14:30:00Z"`.

---

## 3) maze.py — Domain Contract

### 3.1 Public Types

#### Direction (Enum)

| Value | Delta (dr, dc) |
| ----- | ----------------- |
| N     | (-1, 0)           |
| S     | (1, 0)            |
| E     | (0, 1)            |
| W     | (0, -1)           |

Properties: `.dr`, `.dc`, `.opposite`.

#### Position (frozen dataclass)

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

#### CellKind (Enum)

Values: `START`, `EXIT`, `NORMAL`.

#### CellSpec (dataclass)

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

### 3.2 Maze Class — What main.py Relies On

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

| Factory | Description |
| ------- | ----------- |
| `build_3x3_maze() -> Maze` | Deterministic hand-authored 3×3 layout with 2 pillars, 1 pit, 1 potion |
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

**Walls:**

- (0,1)↔(1,1) — blocks the central shortcut
- (2,0)↔(2,1) — forces the player to take a longer path

**Minimum path:** (0,0)→(1,0)→(1,1)→(2,1)→(2,2) — but that skips pillar_a. Collecting both pillars requires visiting (0,2) and (2,1).

### 3.4 Fog of War

Fog-of-war is tracked by `maze.py` as part of run state. `maze.py` must expose a structured snapshot of the *known map* (pure data) for the UI/engine to render. `maze.py` must not render ASCII and must not print.

### 3.5 Maze Run State (MVP)

`maze.py` owns the evolving run state for fog-of-war. The engine stores/loads it as JSON-safe primitives.

```python
@dataclass
class MazeRunState:
    pos: Position
    visited: set[Position]            # all visited locations
    visible: set[Position]            # currently visible locations (e.g., pos + neighbors)
    cleared_blockers: set[str]        # ids of cleared blockers

def start_run(maze: Maze) -> MazeRunState

```

### 3.6 Blockers & Movement Outcomes (MVP)

A movement attempt can be blocked by a thematic blocker (formerly a "door").

```python
@dataclass(frozen=True)
class BlockerSpec:
    blocker_id: str
    at: Position
    direction: Direction
    label: str              # themed name, e.g. "Firewall"

```

### 3.7 Known Map Snapshot (MVP)

Maze provides a structured fog-of-war snapshot for rendering.

```python
def known_map(maze: Maze, state: MazeRunState) -> dict   

```
---

## 4) db.py — Persistence Contract (SQLModel/SQLite)

### 4.1 Record DTOs

**PlayerRecord**

| Field       | Type     |
| ----------- | -------- |
| id          | str (UUID) |
| handle      | str      |
| created_at  | str (ISO-8601) |

**GameRecord**

| Field        | Type     |
| ------------ | -------- |
| id           | str (UUID) |
| player_id    | str      |
| maze_id      | str      |
| maze_version | str      |
| state        | dict[str, Any] (opaque to db) |
| status       | str — "in_progress" or "completed" |
| created_at   | str (ISO-8601) |
| updated_at   | str (ISO-8601) |

**ScoreRecord**

| Field        | Type     |
| ------------ | -------- |
| id           | str (UUID) |
| player_id    | str      |
| game_id      | str      |
| maze_id      | str      |
| maze_version | str      |
| metrics      | dict[str, Any] |
| created_at   | str (ISO-8601) |

### 4.2 Repository Interface (minimum)

main.py depends on an object providing these methods:

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

**Key rule:** `state` is opaque to the DB layer. It stores whatever dict main.py hands it without inspecting or importing maze types.

### 4.3 Engine State Storage (JSON-safe, Opaque to DB)

Although the database backend uses SQLite via SQLModel, the *engine state* is stored as a JSON‑safe dictionary.

- The `state` field in the Game record is opaque to `db.py`.
- `db.py` must not inspect, interpret, or import any maze or engine types.
- The engine (`main.py`) is responsible for converting complex domain objects
  (e.g., `Position`) to and from JSON‑safe structures at the boundary.

This design allows the persistence layer to remain independent of domain logic
while still supporting flexible engine evolution.

### 4.4 How Position Crosses the DB Boundary

```
                main.py (boundary)
maze.Position ──────────────────────► {"row": int, "col": int}
              _pos_to_dict()                     │
                                                 ▼
                                         db.save_game(state)
                                                 │
                                                 ▼
                                         SQLite row (JSON state payload)

              _dict_to_pos()                     │
maze.Position ◄──────────────────────  db.get_game(id).state
```

main.py owns the conversion functions:

- `_pos_to_dict(pos: Position) -> dict`
- `_dict_to_pos(d: dict) -> Position`

db.py never touches Position. It only sees dict data persisted in SQLite.

### 4.5 SQLite Backend (MVP Default)

For the MVP phase, SQLite via SQLModel is the default and required persistence backend.

- All game data (players, games, scores, questions) is stored in an SQLite database.
- Repository initialization is responsible for creating tables if they do not exist.
- No JSON-file-based repository is required for MVP.

This ensures persistence across runs and supports question tracking without repeats.

---

## 5) main.py — Engine + CLI Wiring

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

**Command**

```python
@dataclass
class Command:
    verb: str
    args: list[str]
```

**GameView** (what the UI renders)

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

**GameOutput**

```python
@dataclass
class GameOutput:
    view: GameView
    messages: list[str]
```

### 5.3 CLI Command Grammar (MVP)

| Command | Action |
|--------|--------|
| n / s / e / w | Attempt movement in that direction |
| go <direction> | Alias for movement |
| look | Describe the current location and visible exits |
| map | Display the fog‑of‑war map |
| heal / h | Use a healing item (if available) |
| save | Persist the current game state via the repository |
| quit / q | Save and exit the game |

Note: If a movement attempt is blocked by a thematic blocker, the engine must:
1. Request an unused themed question from the database
2. Prompt the player for an answer
3. Resolve the blocker based on correctness
4. Continue the game loop accordingly

### 5.4 Map Rendering (fog of war)

```
  0   1   2
0  @  |###|###
1 ###|###|###
2 ###|###|###
```

- **@** = player position
- **S** = start (visited)
- **X** = exit (visited)
- **P** = pillar (visited)
- **O** = pit (visited)
- **.** = normal cell (visited)
- **###** = unvisited / fog

---

## 6) Versioning & Compatibility

| Key            | Stored in        | Purpose |
|----------------|------------------|---------|
| maze_id        | Database         | Identifies which maze layout was used |
| maze_version   | Database         | Tracks changes to maze topology or rules |
| schema_version | Database / code  | Tracks database schema changes |

The engine must verify version compatibility when loading persisted game state.  
If any of these version identifiers change, a clear migration or compatibility strategy must be provided before gameplay continues.
