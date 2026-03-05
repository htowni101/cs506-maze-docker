"""
maze.py — Domain Logic (Pure Python)

Isometric dungeon maze: topology, walls, collision, spawn points, NPC placement.

CONSTRAINTS:
  - Cannot import db or main.
  - Cannot use print().
  - Outputs data, not text.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Public Types
# ---------------------------------------------------------------------------

class Direction(Enum):
    """Cardinal movement directions with (row_delta, col_delta)."""
    N = (-1, 0)
    S = (1, 0)
    E = (0, 1)
    W = (0, -1)

    @property
    def dr(self) -> int:
        return self.value[0]

    @property
    def dc(self) -> int:
        return self.value[1]

    @property
    def opposite(self) -> "Direction":
        return _OPPOSITES[self]


_OPPOSITES = {
    Direction.N: Direction.S,
    Direction.S: Direction.N,
    Direction.E: Direction.W,
    Direction.W: Direction.E,
}


@dataclass(frozen=True)
class Position:
    """A (row, col) coordinate on the maze grid."""
    row: int
    col: int

    def moved(self, direction: Direction) -> "Position":
        """Return the Position one step in *direction*."""
        return Position(self.row + direction.dr, self.col + direction.dc)

    def to_dict(self) -> dict:
        """JSON-safe serialisation."""
        return {"row": self.row, "col": self.col}

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(row=d["row"], col=d["col"])


class CellKind(Enum):
    START = "START"
    EXIT = "EXIT"
    NORMAL = "NORMAL"


@dataclass
class CellSpec:
    """Immutable specification of one maze cell."""
    pos: Position
    kind: CellKind = CellKind.NORMAL
    blocked: set[Direction] = field(default_factory=set)
    npc_id: Optional[str] = None            # e.g. "old_weary", "messy_goblin"
    has_pit: bool = False
    has_healing_potion: bool = False
    has_vision_potion: bool = False
    tile_type: Optional[str] = None         # e.g. "floor", "ne_wall", "sw_dead"

    # --- convenience helpers (no print!) ---
    def is_passable(self, direction: Direction) -> bool:
        """True if the adventurer *can* leave this cell in *direction*."""
        return direction not in self.blocked


# ---------------------------------------------------------------------------
# Maze Class
# ---------------------------------------------------------------------------

class Maze:
    """
    A grid-based dungeon maze.

    The maze stores its topology as a dict[Position, CellSpec] so any grid
    size is supported.  Walls are encoded as *blocked directions* on each cell
    (symmetric — if cell A blocks East, cell B to the east blocks West).
    """

    def __init__(
        self,
        maze_id: str,
        maze_version: str,
        width: int,
        height: int,
        cells: dict[Position, CellSpec],
        start: Position,
        exit_pos: Position,
    ):
        self.maze_id = maze_id
        self.maze_version = maze_version
        self.width = width
        self.height = height
        self._cells = cells
        self.start = start
        self.exit = exit_pos

    # --- topology queries ---

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.row < self.height and 0 <= pos.col < self.width

    def cell(self, pos: Position) -> CellSpec:
        """Return the CellSpec at *pos*.  Raises KeyError if out of bounds."""
        return self._cells[pos]

    def available_moves(self, pos: Position) -> set[Direction]:
        """Directions the adventurer can move from *pos*."""
        spec = self._cells[pos]
        moves: set[Direction] = set()
        for d in Direction:
            if d in spec.blocked:
                continue
            dest = pos.moved(d)
            if dest in self._cells:
                moves.add(d)
        return moves

    def next_pos(self, pos: Position, direction: Direction) -> Optional[Position]:
        """
        Return destination Position if the move is physically legal,
        else None.
        """
        if direction not in self.available_moves(pos):
            return None
        return pos.moved(direction)

    def npc_at(self, pos: Position) -> Optional[str]:
        """Return the npc_id at *pos*, or None."""
        spec = self._cells.get(pos)
        return spec.npc_id if spec else None

    def all_positions(self) -> list[Position]:
        """Every valid Position in the maze (useful for rendering)."""
        return list(self._cells.keys())

    def all_cells(self) -> list[CellSpec]:
        """Every CellSpec in the maze."""
        return list(self._cells.values())


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _sym_wall(cells: dict[Position, CellSpec], a: Position, direction: Direction):
    """Add a wall between *a* and the neighbour in *direction* (symmetric)."""
    cells[a].blocked.add(direction)
    b = a.moved(direction)
    if b in cells:
        cells[b].blocked.add(direction.opposite)


def build_3x3_maze() -> Maze:
    """
    Hand-authored, deterministic 3×3 walking-skeleton maze.

    Layout (row, col)::

        (0,0) START ──► (0,1)       ──► (0,2) OLD WEARY
          │               ║ wall            │
          ▼               ║                 ▼
        (1,0) PIT   ──► (1,1)       ──► (1,2) heal potion
          │               │
          ▼               ▼
        (2,0)       ║  (2,1) M.GOBLIN ──► (2,2) EXIT
                    ║ wall

    Walls:
      - (0,1) ↔ (1,1)  — blocks the central shortcut
      - (2,0) ↔ (2,1)  — forces the player to take a longer path

    NPCs:
      - Old Weary at (0,2)  — guard the lever / portcullis
      - Messy Goblin at (2,1)  — knows the door password
    """
    cells: dict[Position, CellSpec] = {}

    # Create all 9 cells
    for r in range(3):
        for c in range(3):
            pos = Position(r, c)
            kind = CellKind.NORMAL
            if (r, c) == (0, 0):
                kind = CellKind.START
            elif (r, c) == (2, 2):
                kind = CellKind.EXIT
            cells[pos] = CellSpec(pos=pos, kind=kind)

    # Place NPCs
    cells[Position(0, 2)].npc_id = "old_weary"
    cells[Position(2, 1)].npc_id = "messy_goblin"

    # Place a pit
    cells[Position(1, 0)].has_pit = True

    # Place a healing potion
    cells[Position(1, 2)].has_healing_potion = True

    # --- Walls (make the maze non-trivial) ---
    # Wall between (0,1) and (1,1) — blocks the direct center path
    _sym_wall(cells, Position(0, 1), Direction.S)
    # Wall between (2,0) and (2,1) — forces player around
    _sym_wall(cells, Position(2, 0), Direction.E)

    start = Position(0, 0)
    exit_pos = Position(2, 2)

    return Maze(
        maze_id="maze-3x3-v1",
        maze_version="1.0",
        width=3,
        height=3,
        cells=cells,
        start=start,
        exit_pos=exit_pos,
    )


def build_square_maze(size: int, seed: int) -> Maze:
    """
    Procedurally generate an *size*×*size* maze using seeded randomness.

    Uses a recursive-backtracker algorithm to carve passages, then places
    pillars and items.  Start is always (0,0), exit is (size-1, size-1).
    """
    rng = random.Random(seed)

    # Start with every cell having all 4 walls
    cells: dict[Position, CellSpec] = {}
    for r in range(size):
        for c in range(size):
            pos = Position(r, c)
            kind = CellKind.NORMAL
            if (r, c) == (0, 0):
                kind = CellKind.START
            elif (r, c) == (size - 1, size - 1):
                kind = CellKind.EXIT
            cells[pos] = CellSpec(
                pos=pos,
                kind=kind,
                blocked=set(Direction),  # all walls initially
            )

    # Recursive backtracker
    visited: set[Position] = set()
    stack: list[Position] = [Position(0, 0)]
    visited.add(Position(0, 0))

    while stack:
        current = stack[-1]
        neighbors = []
        for d in Direction:
            nb = current.moved(d)
            if 0 <= nb.row < size and 0 <= nb.col < size and nb not in visited:
                neighbors.append((d, nb))
        if neighbors:
            d, nb = rng.choice(neighbors)
            # Remove wall between current and nb
            cells[current].blocked.discard(d)
            cells[nb].blocked.discard(d.opposite)
            visited.add(nb)
            stack.append(nb)
        else:
            stack.pop()

    # Place NPCs on random non-start, non-exit cells
    interior = [
        p for p in cells
        if p != Position(0, 0) and p != Position(size - 1, size - 1)
    ]
    rng.shuffle(interior)
    npc_ids = ["old_weary", "messy_goblin"]
    for i, npc_id in enumerate(npc_ids):
        if i < len(interior):
            cells[interior[i]].npc_id = npc_id

    # Place a pit and a healing potion on remaining interior cells
    remaining = interior[len(npc_ids):]
    if remaining:
        cells[remaining[0]].has_pit = True
    if len(remaining) > 1:
        cells[remaining[1]].has_healing_potion = True

    return Maze(
        maze_id=f"maze-{size}x{size}-seed{seed}",
        maze_version="1.0",
        width=size,
        height=size,
        cells=cells,
        start=Position(0, 0),
        exit_pos=Position(size - 1, size - 1),
    )


# ---------------------------------------------------------------------------
# Dungeon-backed factory (procedural rooms + corridors)
# ---------------------------------------------------------------------------

def build_dungeon_maze(
    seed: int,
    width: int = 60,
    height: int = 40,
    max_rooms: int = 12,
    min_room_size: int = 4,
    max_room_size: int = 8,
) -> Maze:
    """
    Generate a procedural dungeon via ``dungeon.generate_dungeon`` and
    wrap it in a :class:`Maze` object.

    Each floor tile (``'.'``) in the dungeon map becomes a :class:`CellSpec`.
    Walls are inferred from adjacency — if a neighbour in a cardinal
    direction is not a floor tile, that direction is blocked.

    Start = centre of the first room.
    Exit  = centre of the last room.
    NPCs are placed in the centres of intermediate rooms.
    """
    # Create a seeded RNG so dungeon.generate_dungeon is deterministic.
    rng = random.Random(seed)

    from dungeon import generate_dungeon  # local import to respect constraints

    dungeon_map, tile_types, rooms = generate_dungeon(
        width, height, max_rooms, min_room_size, max_room_size, rng=rng,
    )

    # Build CellSpec for every floor tile
    cells: dict[Position, CellSpec] = {}
    for row in range(height):
        for col in range(width):
            if dungeon_map[row][col] != '.':
                continue
            pos = Position(row, col)
            blocked: set[Direction] = set()
            for d in Direction:
                nr, nc = row + d.dr, col + d.dc
                if not (0 <= nr < height and 0 <= nc < width):
                    blocked.add(d)
                elif dungeon_map[nr][nc] != '.':
                    blocked.add(d)
            cells[pos] = CellSpec(
                pos=pos,
                blocked=blocked,
                tile_type=tile_types[row][col],
            )

    # Choose start / exit from rooms
    if not rooms:
        # Fallback: pick first and last floor positions
        all_pos = sorted(cells.keys(), key=lambda p: (p.row, p.col))
        start = all_pos[0]
        exit_pos = all_pos[-1]
    else:
        start = Position(rooms[0].center_y, rooms[0].center_x)
        exit_pos = Position(rooms[-1].center_y, rooms[-1].center_x)

    # Ensure start / exit are actually valid floor tiles
    if start not in cells:
        start = min(cells.keys(), key=lambda p: abs(p.row - start.row) + abs(p.col - start.col))
    if exit_pos not in cells:
        exit_pos = min(cells.keys(), key=lambda p: abs(p.row - exit_pos.row) + abs(p.col - exit_pos.col))

    cells[start] = CellSpec(
        pos=start,
        kind=CellKind.START,
        blocked=cells[start].blocked,
        tile_type=cells[start].tile_type,
    )
    cells[exit_pos] = CellSpec(
        pos=exit_pos,
        kind=CellKind.EXIT,
        blocked=cells[exit_pos].blocked,
        tile_type=cells[exit_pos].tile_type,
    )

    # Place NPCs in intermediate rooms
    rng = random.Random(seed)
    npc_ids = ["old_weary", "messy_goblin"]
    npc_rooms = rooms[1:-1] if len(rooms) > 2 else rooms[1:] if len(rooms) > 1 else []
    rng.shuffle(npc_rooms)
    for i, npc_id in enumerate(npc_ids):
        if i >= len(npc_rooms):
            break
        npc_pos = Position(npc_rooms[i].center_y, npc_rooms[i].center_x)
        if npc_pos in cells:
            cells[npc_pos].npc_id = npc_id

    # Place a pit and healing potion in other intermediate rooms
    item_rooms = [r for r in rooms if Position(r.center_y, r.center_x) != start
                  and Position(r.center_y, r.center_x) != exit_pos
                  and Position(r.center_y, r.center_x) in cells
                  and cells[Position(r.center_y, r.center_x)].npc_id is None]
    rng.shuffle(item_rooms)
    if item_rooms:
        pit_pos = Position(item_rooms[0].center_y, item_rooms[0].center_x)
        cells[pit_pos].has_pit = True
    if len(item_rooms) > 1:
        heal_pos = Position(item_rooms[1].center_y, item_rooms[1].center_x)
        cells[heal_pos].has_healing_potion = True

    maze_id = f"dungeon-{width}x{height}-seed{seed}"
    return Maze(
        maze_id=maze_id,
        maze_version="1.0",
        width=width,
        height=height,
        cells=cells,
        start=start,
        exit_pos=exit_pos,
    )
