"""
game_state.py — Pure-Python Game State (no Pygame dependency)

Manages fog of war, NPC tracking, player state, and the NPC registry.
Extracted from game.py so that headless engines and tests can use
GameState without importing Pygame.

CONSTRAINTS:
  - Cannot import db, main, or game.
  - No Pygame imports.
  - Outputs data, not text (no print()).
"""
from __future__ import annotations

import random
from typing import Optional

from maze import Maze, Position, CellKind
from npc_ai import (
    MobileNPC, create_brian_wererat, create_floating_shoe,
    bfs_distance_map,
)
from npc_data import (
    NPCState,
    OLD_WEARY_GREETING, OLD_WEARY_DESCRIPTION,
    OLD_WEARY_CRUEL_ACTIONS, OLD_WEARY_KIND_ACTIONS,
    OLD_WEARY_CRUEL_REACTIONS, OLD_WEARY_KIND_REACTIONS,
    MESSY_GOBLIN_GREETING, MESSY_GOBLIN_DESCRIPTION,
    MESSY_GOBLIN_CRUEL_ACTIONS, MESSY_GOBLIN_KIND_ACTIONS,
    MESSY_GOBLIN_CRUEL_REACTIONS, MESSY_GOBLIN_KIND_REACTIONS,
)


# ---------------------------------------------------------------------------
# NPC Registry — maps npc_id → data bundle
# ---------------------------------------------------------------------------

NPC_REGISTRY: dict[str, dict] = {
    "old_weary": {
        "name": "Old Weary",
        "greeting": OLD_WEARY_GREETING,
        "description": OLD_WEARY_DESCRIPTION,
        "cruel_actions": OLD_WEARY_CRUEL_ACTIONS,
        "kind_actions": OLD_WEARY_KIND_ACTIONS,
        "cruel_reactions": OLD_WEARY_CRUEL_REACTIONS,
        "kind_reactions": OLD_WEARY_KIND_REACTIONS,
        "win_direction": "cruel",
        "win_threshold": -3,
        "fail_threshold": 3,
    },
    "messy_goblin": {
        "name": "Messy Goblin",
        "greeting": MESSY_GOBLIN_GREETING,
        "description": MESSY_GOBLIN_DESCRIPTION,
        "cruel_actions": MESSY_GOBLIN_CRUEL_ACTIONS,
        "kind_actions": MESSY_GOBLIN_KIND_ACTIONS,
        "cruel_reactions": MESSY_GOBLIN_CRUEL_REACTIONS,
        "kind_reactions": MESSY_GOBLIN_KIND_REACTIONS,
        "win_direction": "kind",
        "win_threshold": 3,
        "fail_threshold": -3,
    },
    "lila": {
        "name": "Lila",
        "greeting": MESSY_GOBLIN_GREETING,
        "description": MESSY_GOBLIN_DESCRIPTION,
        "cruel_actions": MESSY_GOBLIN_CRUEL_ACTIONS,
        "kind_actions": MESSY_GOBLIN_KIND_ACTIONS,
        "cruel_reactions": MESSY_GOBLIN_CRUEL_REACTIONS,
        "kind_reactions": MESSY_GOBLIN_KIND_REACTIONS,
        "win_direction": "kind",
        "win_threshold": 3,
        "fail_threshold": -3,
    },
    "giant": {
        "name": "Giant",
        "greeting": MESSY_GOBLIN_GREETING,
        "description": MESSY_GOBLIN_DESCRIPTION,
        "cruel_actions": MESSY_GOBLIN_CRUEL_ACTIONS,
        "kind_actions": MESSY_GOBLIN_KIND_ACTIONS,
        "cruel_reactions": MESSY_GOBLIN_CRUEL_REACTIONS,
        "kind_reactions": MESSY_GOBLIN_KIND_REACTIONS,
        "win_direction": "kind",
        "win_threshold": 3,
        "fail_threshold": -3,
    },
    "knight": {
        "name": "Knight",
        "greeting": MESSY_GOBLIN_GREETING,
        "description": MESSY_GOBLIN_DESCRIPTION,
        "cruel_actions": MESSY_GOBLIN_CRUEL_ACTIONS,
        "kind_actions": MESSY_GOBLIN_KIND_ACTIONS,
        "cruel_reactions": MESSY_GOBLIN_CRUEL_REACTIONS,
        "kind_reactions": MESSY_GOBLIN_KIND_REACTIONS,
        "win_direction": "kind",
        "win_threshold": 3,
        "fail_threshold": -3,
    },
}


class GameState:
    """Manages fog of war, NPC tracking, and player state backed by a Maze."""

    def __init__(self, maze: Maze, seed: int = 0):
        self.maze = maze
        self.seed = seed
        self.rng = random.Random(seed)

        # Build 2D arrays from Maze so the render pipeline stays unchanged
        self.height = maze.height
        self.width = maze.width
        self.dungeon_map = [['#'] * maze.width for _ in range(maze.height)]
        self.tile_types = [[None] * maze.width for _ in range(maze.height)]
        for cell in maze.all_cells():
            r, c = cell.pos.row, cell.pos.col
            self.dungeon_map[r][c] = '.'
            self.tile_types[r][c] = cell.tile_type or 'floor'

        # Per-position fog of war  (True == fogged)
        self.fog: dict[Position, bool] = {
            pos: True for pos in maze.all_positions()
        }

        # Player state
        self.pos: Position = maze.start
        self.hp: int = 100
        self.max_hp: int = 100
        self.will: int = 10
        self.max_will: int = 10
        self.healing_potions: int = 0
        self.vision_potions: int = 0
        self.will_potions: int = 0
        self.move_count: int = 0
        self.sprite_direction: str = 'SW'
        self.visited: set[Position] = set()
        self.is_complete: bool = False
        self.is_dead: bool = False

        # NPC states
        self.npc_states: dict[str, NPCState] = {}
        self.npc_greeted: set[str] = set()
        for cell in maze.all_cells():
            if cell.npc_id and cell.npc_id in NPC_REGISTRY:
                self.npc_states[cell.npc_id] = NPCState(npc_id=cell.npc_id)

        # Consumed items
        self.consumed_potions: set[Position] = set()
        self.triggered_pits: set[Position] = set()

        # Mobile NPCs
        self.mobile_npcs: list[MobileNPC] = self._place_mobile_npcs(seed)

        # Clear fog at start
        self._visit(maze.start)

    # -- fog helpers --

    def _visit(self, pos: Position):
        self.visited.add(pos)
        self.clear_fog_radius(pos, radius=2)

    def clear_fog_at(self, pos: Position):
        if pos in self.fog:
            self.fog[pos] = False

    def clear_fog_radius(self, center: Position, radius: int = 2):
        for pos, _fogged in self.fog.items():
            if abs(pos.row - center.row) + abs(pos.col - center.col) <= radius:
                self.fog[pos] = False

    def clear_fog_nearest_cluster(self) -> bool:
        """Reveal nearest cluster of fogged cells (vision potion)."""
        fogged = [p for p, f in self.fog.items() if f]
        if not fogged:
            return False
        nearest = min(
            fogged,
            key=lambda p: abs(p.row - self.pos.row) + abs(p.col - self.pos.col),
        )
        self.clear_fog_radius(nearest, radius=4)
        return True

    def is_fogged(self, pos: Position) -> bool:
        return self.fog.get(pos, True)

    def _place_mobile_npcs(self, seed: int) -> list[MobileNPC]:
        """Pick spawn positions for mobile NPCs in rooms far from start/exit."""
        rng = random.Random(seed + 99)
        start = self.maze.start
        exit_pos = self.maze.exit

        # Build distance map from start to find tiles far from start
        dist_from_start = bfs_distance_map(self.maze, start)

        # Candidate tiles: floor cells with no static NPC, not start/exit
        candidates = []
        for cell in self.maze.all_cells():
            p = cell.pos
            if p == start or p == exit_pos:
                continue
            if cell.npc_id:  # has a static NPC
                continue
            if cell.has_pit:
                continue
            d = dist_from_start.get(p, 0)
            if d >= 5:  # at least 5 tiles from start
                candidates.append((p, d))

        # Sort by distance descending, pick two well-separated positions
        candidates.sort(key=lambda x: -x[1])
        npcs: list[MobileNPC] = []

        if candidates:
            brian_pos = candidates[rng.randint(0, min(5, len(candidates) - 1))][0]
            npcs.append(create_brian_wererat(brian_pos))

            # For shoe, pick a position far from Brian too
            shoe_candidates = [
                (p, d) for p, d in candidates
                if abs(p.row - brian_pos.row) + abs(p.col - brian_pos.col) >= 4
            ]
            if not shoe_candidates:
                shoe_candidates = candidates
            shoe_pos = shoe_candidates[rng.randint(0, min(5, len(shoe_candidates) - 1))][0]
            npcs.append(create_floating_shoe(shoe_pos))

        return npcs

    def all_npcs_resolved(self) -> bool:
        if not self.npc_states:
            return True
        return all(ns.resolved for ns in self.npc_states.values())
