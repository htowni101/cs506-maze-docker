"""
npc_ai.py — Mobile NPC system with BFS pathfinding and smooth movement.

Provides autonomous NPCs that chase or flee the player on the maze grid.
Movement uses a hybrid approach: discrete BFS pathfinding for decisions,
smooth float interpolation for rendering.
"""
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from maze import Maze, Position, Direction


# ---------------------------------------------------------------------------
# BFS Pathfinding
# ---------------------------------------------------------------------------

def bfs_path(maze: Maze, start: Position, goal: Position) -> list[Position]:
    """Return shortest path from *start* to *goal* (inclusive of both).

    Uses ``maze.available_moves()`` to respect walls.
    Returns [] if unreachable.
    """
    if start == goal:
        return [start]

    visited: set[Position] = {start}
    parent: dict[Position, Position] = {}
    queue: deque[Position] = deque([start])

    while queue:
        pos = queue.popleft()
        for d in maze.available_moves(pos):
            nb = pos.moved(d)
            if nb in visited:
                continue
            try:
                maze.cell(nb)
            except KeyError:
                continue
            visited.add(nb)
            parent[nb] = pos
            if nb == goal:
                # Reconstruct
                path = [nb]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path
            queue.append(nb)
    return []


def bfs_distance_map(maze: Maze, origin: Position) -> dict[Position, int]:
    """BFS flood-fill from *origin*. Returns {pos: distance} for all reachable cells."""
    dist: dict[Position, int] = {origin: 0}
    queue: deque[Position] = deque([origin])

    while queue:
        pos = queue.popleft()
        d_cur = dist[pos]
        for d in maze.available_moves(pos):
            nb = pos.moved(d)
            if nb in dist:
                continue
            try:
                maze.cell(nb)
            except KeyError:
                continue
            dist[nb] = d_cur + 1
            queue.append(nb)
    return dist


# ---------------------------------------------------------------------------
# Direction helpers (for facing calculation)
# ---------------------------------------------------------------------------

_DR_DC_TO_FACING: dict[tuple[int, int], str] = {
    (-1, 0): 'N', (1, 0): 'S', (0, -1): 'W', (0, 1): 'E',
    (-1, -1): 'NW', (-1, 1): 'NE', (1, -1): 'SW', (1, 1): 'SE',
}


def _facing_from_delta(dr: float, dc: float) -> str:
    sr = -1 if dr < 0 else (1 if dr > 0 else 0)
    sc = -1 if dc < 0 else (1 if dc > 0 else 0)
    return _DR_DC_TO_FACING.get((sr, sc), 'S')


# ---------------------------------------------------------------------------
# MobileNPC
# ---------------------------------------------------------------------------

@dataclass
class MobileNPC:
    """A mobile NPC that moves through the maze autonomously."""

    npc_id: str
    name: str
    behavior: str               # "chase" or "flee"
    speed: float                # tiles per second

    # Current discrete tile (for pathfinding / game logic)
    pos: Position = field(default_factory=lambda: Position(0, 0))

    # Smooth float position (for rendering)
    float_row: float = 0.0
    float_col: float = 0.0

    # Movement state
    target_pos: Optional[Position] = None   # next tile to move toward
    path: list[Position] = field(default_factory=list)
    path_recalc_timer: float = 0.0          # seconds until next BFS recalc
    facing: str = 'S'

    # Behavior tuning
    activation_range: int = 8       # chase starts within this range
    flee_trigger_range: int = 2     # flee starts within this range
    active: bool = False            # currently pursuing behavior

    # Interaction state
    kindness_count: int = 0
    resolved: bool = False
    reward_given: bool = False

    # Rendering
    color: tuple[int, int, int] = (255, 0, 0)
    shape: str = "diamond"          # "diamond" or "circle"
    bob_phase: float = 0.0         # for floating animation
    bite_cooldown: float = 0.0     # seconds until next bite allowed

    def manhattan_to(self, row: float, col: float) -> float:
        return abs(self.float_row - row) + abs(self.float_col - col)

    def init_position(self, pos: Position):
        """Place NPC at a tile center."""
        self.pos = pos
        self.float_row = pos.row + 0.5
        self.float_col = pos.col + 0.5


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def create_brian_wererat(pos: Position) -> MobileNPC:
    npc = MobileNPC(
        npc_id="brian_wererat",
        name="Torren the Guard",
        behavior="chase",
        speed=2.8,
        activation_range=8,
        color=(200, 50, 50),
        shape="diamond",
    )
    npc.init_position(pos)
    return npc


def create_floating_shoe(pos: Position) -> MobileNPC:
    npc = MobileNPC(
        npc_id="floating_shoe",
        name="Vargo the Merchant",
        behavior="flee",
        speed=2.5,
        flee_trigger_range=2,
        color=(180, 80, 220),
        shape="circle",
    )
    npc.init_position(pos)
    return npc


# ---------------------------------------------------------------------------
# Per-frame update
# ---------------------------------------------------------------------------

# How often to recalculate BFS (seconds) — throttled to ~4 Hz
PATH_RECALC_INTERVAL = 0.25


def update_mobile_npcs(
    npcs: list[MobileNPC],
    maze: Maze,
    player_row: float,
    player_col: float,
    dt_s: float,
):
    """Per-frame update for all mobile NPCs."""
    player_tile = Position(math.floor(player_row), math.floor(player_col))

    for npc in npcs:
        if npc.resolved:
            continue

        npc.bob_phase += dt_s * 3.0  # for floating animation

        dist = npc.manhattan_to(player_row, player_col)

        # Activation check
        if npc.behavior == "chase":
            npc.active = dist <= npc.activation_range
        elif npc.behavior == "flee":
            npc.active = dist <= npc.flee_trigger_range

        if not npc.active:
            continue

        # Path recalculation timer
        npc.path_recalc_timer -= dt_s
        if npc.path_recalc_timer <= 0:
            npc.path_recalc_timer = PATH_RECALC_INTERVAL
            _recalculate_path(npc, maze, player_tile)

        # Smooth movement toward target
        _move_toward_target(npc, maze, dt_s)


def _recalculate_path(npc: MobileNPC, maze: Maze, player_tile: Position):
    """Recompute the NPC's path based on behavior."""
    if npc.behavior == "chase":
        path = bfs_path(maze, npc.pos, player_tile)
        if len(path) > 1:
            npc.path = path[1:]  # skip current position
        else:
            npc.path = []

    elif npc.behavior == "flee":
        # Pick the neighbor that maximizes distance from player
        dist_map = bfs_distance_map(maze, player_tile)
        best_pos = None
        best_dist = dist_map.get(npc.pos, 0)

        for d in maze.available_moves(npc.pos):
            nb = npc.pos.moved(d)
            try:
                maze.cell(nb)
            except KeyError:
                continue
            nb_dist = dist_map.get(nb, 0)
            if nb_dist > best_dist:
                best_dist = nb_dist
                best_pos = nb

        if best_pos is not None:
            npc.path = [best_pos]
        else:
            npc.path = []


def _move_toward_target(npc: MobileNPC, maze: Maze, dt_s: float):
    """Smoothly interpolate NPC float position toward the next path tile."""
    # Pick next target from path
    if npc.target_pos is None and npc.path:
        npc.target_pos = npc.path.pop(0)

    if npc.target_pos is None:
        return

    # Target center of the tile
    target_row = npc.target_pos.row + 0.5
    target_col = npc.target_pos.col + 0.5

    dr = target_row - npc.float_row
    dc = target_col - npc.float_col
    dist = math.hypot(dr, dc)

    if dist < 0.05:
        # Arrived at target tile
        npc.float_row = target_row
        npc.float_col = target_col
        npc.pos = npc.target_pos
        npc.target_pos = None
        return

    # Update facing
    npc.facing = _facing_from_delta(dr, dc)

    # Move toward target
    step = npc.speed * dt_s
    if step >= dist:
        npc.float_row = target_row
        npc.float_col = target_col
        npc.pos = npc.target_pos
        npc.target_pos = None
    else:
        npc.float_row += (dr / dist) * step
        npc.float_col += (dc / dist) * step


# ---------------------------------------------------------------------------
# Interaction helpers (called from game.py)
# ---------------------------------------------------------------------------

def nearest_mobile_npc_in_range(
    npcs: list[MobileNPC],
    player_row: float,
    player_col: float,
    radius: float = 2.0,
) -> Optional[MobileNPC]:
    """Return the closest non-resolved mobile NPC within *radius*, or None."""
    best: Optional[MobileNPC] = None
    best_dist = radius + 1
    for npc in npcs:
        if npc.resolved:
            continue
        d = npc.manhattan_to(player_row, player_col)
        if d <= radius and d < best_dist:
            best = npc
            best_dist = d
    return best


def interact_mobile_npc(npc: MobileNPC, side: str, game_state) -> str:
    """Handle K/C interaction with a mobile NPC. Returns dialogue text."""
    if npc.npc_id == "brian_wererat":
        return _interact_brian(npc, side, game_state)
    elif npc.npc_id == "floating_shoe":
        return _interact_shoe(npc, side, game_state)
    return ""


def _interact_brian(npc: MobileNPC, side: str, gs) -> str:
    """Torren the Guard: K x3 = 10 will potions. C = 70 damage."""
    if side == "kind":
        npc.kindness_count += 1
        remaining = 3 - npc.kindness_count
        if npc.kindness_count >= 3:
            npc.resolved = True
            npc.reward_given = True
            npc.active = False
            gs.will_potions += 10
            return (
                "Torren lowers his spear and straightens his posture.\n"
                '"You showed honor. Take these and keep moving."\n'
                "[Torren gives you 10 will potions! Press W to use.]"
            )
        else:
            return (
                f"Torren hesitates, surprised by your restraint.\n"
                f'"Not many travelers choose mercy down here." ({remaining} more to go)'
            )
    else:  # cruel
        damage = 70
        gs.hp = max(0, gs.hp - damage)
        return (
            f"Torren strikes fast with his spear and hits you for {damage} damage!\n"
            '"Stand down, or the next one goes through your armor."'
        )


def _interact_shoe(npc: MobileNPC, side: str, gs) -> str:
    """Vargo merchant encounter on the floating_shoe slot."""
    if side == "kind":
        npc.resolved = True
        npc.reward_given = True
        npc.active = False
        gs.vision_potions += 3
        return (
            "Vargo smooths his coat and gives a polished smile.\n"
            '"A wise customer and a fair deal. Take these for the road."\n'
            "[Vargo gives you 3 vision potions!]"
        )
    else:  # cruel
        npc.speed = min(npc.speed + 0.5, 4.0)  # temporarily faster
        return (
            "Vargo snaps his ledger shut and backs away quickly.\n"
            '"Then there is no business to be done here."'
        )
