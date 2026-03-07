"""
game.py — Pygame Isometric Dungeon Game

Integrates maze.py topology with isometric rendering, NPC emotion system,
and fog of war.  Win condition: resolve both NPCs to unlock the exit.
"""
import math
import pygame
import sys
import os
import random
from pathlib import Path
from typing import Optional

from maze import Maze, Position, Direction, CellSpec, CellKind
from sprite_animation import SpriteAnimator
from ui_panel import UIPanel
from npc_ai import (
    MobileNPC, create_brian_wererat, create_floating_shoe,
    update_mobile_npcs, nearest_mobile_npc_in_range,
    interact_mobile_npc, bfs_distance_map,
)
from npc_data import (
    NPCState,
    pick_action_and_category,
    get_reaction,
    category_for_side,
    EMOTION_LABELS,
    OLD_WEARY_GREETING, OLD_WEARY_DESCRIPTION,
    OLD_WEARY_CRUEL_ACTIONS, OLD_WEARY_KIND_ACTIONS,
    OLD_WEARY_CRUEL_REACTIONS, OLD_WEARY_KIND_REACTIONS,
    MESSY_GOBLIN_GREETING, MESSY_GOBLIN_DESCRIPTION,
    MESSY_GOBLIN_CRUEL_ACTIONS, MESSY_GOBLIN_KIND_ACTIONS,
    MESSY_GOBLIN_CRUEL_REACTIONS, MESSY_GOBLIN_KIND_REACTIONS,
)


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


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


class Game:
    """Main game controller — accepts a Maze, renders isometrically, NPC interaction."""

    # Velocity vectors in tile-coordinate space (row_delta, col_delta)
    # Mapped so that screen-relative directions feel correct under the
    # isometric projection:  screen_x ∝ (col-row), screen_y ∝ (col+row)
    _VELOCITY_MAP: dict[str, tuple[float, float]] = {
        'up':    (-1, -1), 'down':  ( 1,  1),
        'left':  ( 1, -1), 'right': (-1,  1),
        'kp8':   (-1, -1), 'kp2':   ( 1,  1),
        'kp4':   ( 1, -1), 'kp6':   (-1,  1),
        'kp9':   (-1,  0), 'kp7':   ( 0, -1),
        'kp3':   ( 0,  1), 'kp1':   ( 1,  0),
    }

    # Velocity sign → sprite-sheet compass facing
    # (signs refer to the screen-relative velocity after iso rotation)
    _SIGN_TO_FACING: dict[tuple[int, int], str] = {
        (-1, -1): 'N',  ( 1,  1): 'S',
        ( 1, -1): 'W',  (-1,  1): 'E',
        (-1,  0): 'NE', ( 0, -1): 'NW',
        ( 0,  1): 'SE', ( 1,  0): 'SW',
    }

    # All direction key names (for held-key tracking)
    _ALL_DIR_KEYS = set(_VELOCITY_MAP.keys())

    # Smooth-movement tuning
    PLAYER_SPEED = 3.5   # tiles per second
    TILE_MARGIN  = 0.05  # stop this far from a blocked edge

    def __init__(
        self,
        maze: Maze,
        seed: int = 0,
        screen_width: int = 1200,
        screen_height: int = 800,
        repo=None,
        player_name: str = "Hero",
    ):
        pygame.init()
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("The White Witch's Labyrinth")
        self.clock = pygame.time.Clock()
        self.running = True
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.maze = maze
        self.seed = seed
        self.repo = repo
        self.player_name = player_name

        # Load assets
        self.assets = self._load_assets()

        # Zoom
        self.debug_scale = 1.0
        self.tile_w = int(128 * self.debug_scale)
        self.tile_h = int(75 * self.debug_scale)
        self._scaled_assets_cache: dict = {}

        # Input
        self.keys_held: set[str] = set()

        # Messages / NPC dialogue
        self.message_text: Optional[str] = None
        self.message_time: int = 0
        self.message_duration: int = 180  # frames (3 s @ 60 FPS)
        self.npc_dialogue: Optional[str] = None  # shown while on NPC cell
        self.npc_dialogue_time: int = 0

        # Win / death state
        self.won = False
        self.dead = False
        self.death_fade_time = 0
        self.death_fade_duration = 180
        self.death_drip_time = 0
        self.death_drip_duration = 180
        self.try_again_button: Optional[pygame.Rect] = None

        # Game state
        self.game_state = GameState(maze, seed)

        # HUD
        self.ui_panel = UIPanel(screen_width, screen_height)

        # Camera
        self.camera_x = 0.0
        self.camera_y = 0.0

        # Smooth player position (float tile-coordinates, centre of tile)
        start = self.game_state.pos
        self.player_row: float = start.row + 0.5
        self.player_col: float = start.col + 0.5

        # Sprite animator
        sheet_path = Path(get_resource_path('assets')) / 'sprte sheet isometric silhouette.png'
        if not sheet_path.exists():
            sheet_path = Path(__file__).parent / 'assets' / 'sprte sheet isometric silhouette.png'
        self.animator = SpriteAnimator(str(sheet_path), fps=10)

        # Pre-build sorted tile list for rendering
        self._sorted_tiles = self._build_sorted_tile_list()

    # ------------------------------------------------------------------
    # Asset loading
    # ------------------------------------------------------------------

    def _build_sorted_tile_list(self):
        tiles = []
        gs = self.game_state
        for row in range(gs.height):
            for col in range(gs.width):
                if gs.dungeon_map[row][col] == '.':
                    tt = gs.tile_types[row][col]
                    tiles.append((col, row, tt))
        tiles.sort(key=lambda t: (t[0] + t[1], t[0]))
        return tiles

    def _load_assets(self):
        assets = {}
        assets_path = Path(get_resource_path('assets'))
        if not assets_path.exists():
            assets_path = Path(__file__).parent / 'assets'

        asset_files = [
            'floor_tile_s.png', 'n_corner_s.png', 'e_corner_s.png',
            's_corner_s.png', 'w_corner_s.png',
            'ne_wall_s.png', 'se_wall_s.png', 'sw_wall_s.png', 'nw_wall_s.png',
            'ne_hall_s.png', 'nw_hall_s.png',
            'ne_dead_s.png', 'se_dead_s.png', 'sw_dead_s.png', 'nw_dead_s.png',
            'pillar_b_s.png', 'pillar_g_s.png', 'pillar_p_s.png', 'pillar_y_s.png',
            'potion_h_s.png', 'potion_t_s.png', 'pit.png',
            'nw_hero_s.png', 'ne_hero_s.png', 'sw_hero_s.png', 'se_hero_s.png',
            'fog_n.png', 'fog_e.png', 'fog_s.png', 'fog_w.png',
            'fog_ne.png', 'fog_se.png', 'fog_sw.png', 'fog_nw.png', 'fog_c.png',
            'nw_door_o_s.png', 'ne_door_o_s.png',
            'nw_door_c_s.png', 'ne_door_c_s.png',
        ]
        for fn in asset_files:
            fp = assets_path / fn
            if fp.exists():
                try:
                    assets[fn] = pygame.image.load(str(fp)).convert_alpha()
                except Exception as e:
                    print(f"Error loading {fn}: {e}")
        return assets

    def _get_asset(self, key):
        surf = self.assets.get(key)
        if surf is None:
            return None
        if self.debug_scale == 1:
            return surf
        cached = self._scaled_assets_cache.get(key)
        if cached:
            return cached
        w = max(1, int(surf.get_width() * self.debug_scale))
        h = max(1, int(surf.get_height() * self.debug_scale))
        scaled = pygame.transform.smoothscale(surf, (w, h))
        self._scaled_assets_cache[key] = scaled
        return scaled

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.dead and self.try_again_button:
                    if self.try_again_button.collidepoint(event.pos):
                        self.restart_game()
            elif event.type == pygame.KEYDOWN:
                key_name = self._pygame_key_to_dir(event.key)
                if key_name:
                    self.keys_held.add(key_name)
                elif event.key == pygame.K_h:
                    self._use_healing_potion()
                elif event.key == pygame.K_v:
                    self._use_vision_potion()
                elif event.key == pygame.K_w:
                    self._use_will_potion()
                elif event.key == pygame.K_k:
                    self._interact_npc("kind")
                elif event.key == pygame.K_c:
                    self._interact_npc("cruel")
                elif event.key == pygame.K_ESCAPE:
                    self.running = False
            elif event.type == pygame.KEYUP:
                key_name = self._pygame_key_to_dir(event.key)
                if key_name:
                    self.keys_held.discard(key_name)

    # ------------------------------------------------------------------
    # Key mapping helper
    # ------------------------------------------------------------------

    _KEY_TO_DIR: dict[int, str] = {
        pygame.K_UP: 'up', pygame.K_DOWN: 'down',
        pygame.K_LEFT: 'left', pygame.K_RIGHT: 'right',
        pygame.K_KP8: 'kp8', pygame.K_KP2: 'kp2',
        pygame.K_KP4: 'kp4', pygame.K_KP6: 'kp6',
        pygame.K_KP9: 'kp9', pygame.K_KP7: 'kp7',
        pygame.K_KP3: 'kp3', pygame.K_KP1: 'kp1',
    }

    @classmethod
    def _pygame_key_to_dir(cls, key: int) -> Optional[str]:
        return cls._KEY_TO_DIR.get(key)

    # ------------------------------------------------------------------
    # Smooth movement & collision
    # ------------------------------------------------------------------

    def _is_floor(self, row: int, col: int) -> bool:
        """True when (row, col) is inside the map and walkable."""
        gs = self.game_state
        if row < 0 or col < 0 or row >= gs.height or col >= gs.width:
            return False
        return gs.dungeon_map[row][col] == '.'

    def _can_pass(self, from_r: int, from_c: int, to_r: int, to_c: int) -> bool:
        """True when the maze allows movement from one tile to an adjacent one."""
        if from_r == to_r and from_c == to_c:
            return True
        dr, dc = to_r - from_r, to_c - from_c
        dmap = {(-1, 0): Direction.N, (1, 0): Direction.S,
                (0, -1): Direction.W, (0, 1): Direction.E}
        d = dmap.get((dr, dc))
        if d is None:
            return False
        return self.maze.next_pos(Position(from_r, from_c), d) is not None

    def _try_axis(self, cur: float, delta: float, other_axis: float,
                  axis_is_row: bool) -> float:
        """Move along one axis, respecting tile-boundary walls.

        Returns the new coordinate after collision clamping.
        """
        new = cur + delta
        old_tile = math.floor(cur)
        new_tile = math.floor(new)
        margin = self.TILE_MARGIN

        if old_tile == new_tile:
            return new  # still inside the same tile

        # Determine from/to tile coords for boundary check
        if axis_is_row:
            from_r, from_c = old_tile, math.floor(other_axis)
            to_r, to_c = new_tile, from_c
        else:
            from_r, from_c = math.floor(other_axis), old_tile
            to_r, to_c = from_r, new_tile

        if self._is_floor(to_r, to_c) and self._can_pass(from_r, from_c, to_r, to_c):
            return new  # passage allowed

        # Blocked — clamp to old tile boundary
        if delta > 0:
            return float(old_tile) + 1.0 - margin
        else:
            return float(old_tile) + margin

    def _update_movement(self, dt_s: float):
        """Per-frame smooth movement with wall collision."""
        gs = self.game_state
        if gs.is_dead or gs.is_complete:
            return

        # Sum velocity from all held direction keys
        vr, vc = 0.0, 0.0
        for key in self.keys_held:
            v = self._VELOCITY_MAP.get(key)
            if v:
                vr += v[0]
                vc += v[1]
        if vr == 0.0 and vc == 0.0:
            return

        # Normalise so diagonals aren't faster
        mag = math.hypot(vr, vc)
        vr /= mag
        vc /= mag

        # Update sprite facing
        sr = -1 if vr < 0 else (1 if vr > 0 else 0)
        sc = -1 if vc < 0 else (1 if vc > 0 else 0)
        facing = self._SIGN_TO_FACING.get((sr, sc))
        if facing:
            gs.sprite_direction = facing
            self.animator.set_direction(facing)

        # Apply movement (axis-separated for wall sliding)
        step = self.PLAYER_SPEED * dt_s
        self.player_col = self._try_axis(
            self.player_col, vc * step, self.player_row, axis_is_row=False)
        self.player_row = self._try_axis(
            self.player_row, vr * step, self.player_col, axis_is_row=True)

        # Detect tile change → fire game events
        new_tile = Position(math.floor(self.player_row),
                            math.floor(self.player_col))
        if new_tile != gs.pos:
            gs.pos = new_tile
            gs.move_count += 1
            gs._visit(new_tile)
            self._on_enter_cell(new_tile)

    def _on_enter_cell(self, pos: Position):
        """Handle items, pits, NPCs, exit at the new cell."""
        gs = self.game_state
        cell = self.maze.cell(pos)

        # Pit damage
        if cell.has_pit and pos not in gs.triggered_pits:
            gs.triggered_pits.add(pos)
            damage = gs.rng.randint(1, 20)
            gs.hp = max(0, gs.hp - damage)
            self._show_message(f"Fell in pit! -{damage} HP")
            if gs.hp <= 0:
                gs.is_dead = True
                self.dead = True
                self.death_fade_time = 0
                self.death_drip_time = 0
                return

        # Healing potion pickup
        if cell.has_healing_potion and pos not in gs.consumed_potions:
            gs.consumed_potions.add(pos)
            gs.healing_potions += 1
            self._show_message("Found healing potion!")

        # Vision potion pickup
        if cell.has_vision_potion and pos not in gs.consumed_potions:
            gs.consumed_potions.add(pos)
            gs.vision_potions += 1
            self._show_message("Found vision potion!")

        # NPC greeting (first visit)
        npc_id = cell.npc_id
        if npc_id and npc_id in NPC_REGISTRY and npc_id not in gs.npc_greeted:
            gs.npc_greeted.add(npc_id)
            info = NPC_REGISTRY[npc_id]
            self.npc_dialogue = f"{info['name']}: {info['greeting']}"
            self.npc_dialogue_time = 300  # 5 s

        # Exit check
        if cell.kind == CellKind.EXIT:
            if gs.all_npcs_resolved():
                gs.is_complete = True
                self.won = True
            else:
                unresolved = sum(1 for ns in gs.npc_states.values() if not ns.resolved)
                self._show_message(
                    f"Exit locked! Resolve {unresolved} NPC{'s' if unresolved != 1 else ''} first."
                )

    # ------------------------------------------------------------------
    # NPC interaction (with reversal / puzzled / calming rules)
    # ------------------------------------------------------------------

    def _nearest_npc_id_in_range(self, radius: int = 4) -> Optional[str]:
        """Return npc_id of the closest NPC within *radius* tiles, or None.

        Checks both static (cell-based) and mobile NPCs.
        """
        # Static NPCs
        result = UIPanel.nearest_npc_in_range(
            self.player_row, self.player_col,
            self.maze, self.game_state.npc_states, radius,
        )
        static_id = result[0] if result else None
        static_dist = (abs(result[1].row - self.player_row)
                       + abs(result[1].col - self.player_col)) if result else radius + 1

        # Mobile NPCs
        mobile = nearest_mobile_npc_in_range(
            self.game_state.mobile_npcs,
            self.player_row, self.player_col, float(radius),
        )
        mobile_dist = mobile.manhattan_to(self.player_row, self.player_col) if mobile else radius + 1

        # Return whichever is closer
        if mobile and mobile_dist < static_dist:
            return mobile.npc_id
        return static_id

    def _interact_npc(self, side: str):
        """Called when player presses K(ind) or C(ruel).

        Uses proximity (4 tiles) instead of requiring player to stand on
        the NPC cell.  Implements full reversal / puzzled / calming rules.
        Also handles mobile NPCs (Brian, Floating Shoe).
        """
        gs = self.game_state

        # --- Check mobile NPCs first (within 2 tiles) ---
        mobile = nearest_mobile_npc_in_range(
            gs.mobile_npcs, self.player_row, self.player_col, 2.0,
        )
        if mobile:
            dialogue = interact_mobile_npc(mobile, side, gs)
            if dialogue:
                self.npc_dialogue = dialogue
                self.npc_dialogue_time = 300
            # Check death from Brian's cruelty
            if gs.hp <= 0:
                gs.is_dead = True
                self.dead = True
                self.death_fade_time = 0
                self.death_drip_time = 0
            return

        # --- will check ---
        if gs.will <= 0:
            self._show_message("You lack the will to continue…")
            return

        # --- proximity lookup ---
        npc_id = self._nearest_npc_id_in_range(radius=4)
        if not npc_id or npc_id not in NPC_REGISTRY:
            return
        npc_state = gs.npc_states.get(npc_id)
        if npc_state is None or npc_state.resolved:
            return

        info = NPC_REGISTRY[npc_id]
        name = info["name"]
        es = npc_state.emotional_state  # snapshot *before* any change

        # ---------------------------------------------------------------
        # Reversal rule 1: positive → cruel  (puzzled, then drop to -1)
        # ---------------------------------------------------------------
        if side == "cruel" and npc_state.last_side == "kind" and es > 0:
            if not npc_state.is_puzzled:
                # First reversal press → puzzled, no state change
                npc_state.is_puzzled = True
                npc_state.last_side = side
                gs.will -= 1
                self.npc_dialogue = f"{name} is puzzled."
                self.npc_dialogue_time = 300
                return
            else:
                # Second press while puzzled → drop to -1
                npc_state.is_puzzled = False
                npc_state.emotional_state = -1
                npc_state.was_negative = True
                npc_state.calming_stall_used = False
                npc_state.last_side = side
                npc_state.interaction_count += 1
                gs.will -= 1
                # Get a -1 cruel reaction
                reactions = info["cruel_reactions"]
                category, action_text = pick_action_and_category(info["cruel_actions"], rng=gs.rng)
                category = category_for_side(category, want_positive=False)
                npc_state.last_emotion_category = category
                reaction = get_reaction(reactions, category, 1)
                label = EMOTION_LABELS.get(category, category)
                lines = [f"You chose cruelness → {action_text}"]
                if reaction:
                    lines.append(f"{name} ({label} -1): {reaction}")
                self._check_resolution(npc_state, info, gs)
                self.npc_dialogue = "\n".join(lines)
                self.npc_dialogue_time = 300
                return

        # ---------------------------------------------------------------
        # Reversal rule 2: calming stall at 0 (was_negative)
        # ---------------------------------------------------------------
        if side == "kind" and es == 0 and npc_state.was_negative:
            if not npc_state.calming_stall_used:
                # First K at 0 coming from negative → "calming down"
                # This is the *arrival* at 0; show the calming message
                npc_state.calming_stall_used = True
                npc_state.last_side = side
                gs.will -= 1
                self.npc_dialogue = f"{name} is starting to calm down."
                self.npc_dialogue_time = 300
                return
            elif not npc_state.is_puzzled:
                # Second K at 0 → puzzled stall
                npc_state.is_puzzled = True
                npc_state.last_side = side
                gs.will -= 1
                self.npc_dialogue = f"{name} is puzzled."
                self.npc_dialogue_time = 300
                return
            else:
                # Third K at 0 → break through to +1
                npc_state.is_puzzled = False
                # fall through to normal apply_kindness below

        # ---------------------------------------------------------------
        # Normal interaction
        # ---------------------------------------------------------------
        gs.will -= 1
        npc_state.is_puzzled = False  # clear any leftover puzzled
        actions = info["kind_actions"] if side == "kind" else info["cruel_actions"]
        reactions = info["kind_reactions"] if side == "kind" else info["cruel_reactions"]

        # Pick action
        category, action_text = pick_action_and_category(actions, rng=gs.rng)
        category = category_for_side(category, want_positive=(side == "kind"))

        # Apply effect
        if side == "kind":
            new_state = npc_state.apply_kindness()
        else:
            new_state = npc_state.apply_cruelty()

        npc_state.last_side = side
        npc_state.last_emotion_category = category

        # Track was_negative
        if new_state < 0:
            npc_state.was_negative = True
        # Reset calming stall if we leave 0
        if new_state != 0:
            npc_state.calming_stall_used = False

        # Get reaction
        intensity = abs(new_state)
        reaction = get_reaction(reactions, category, intensity) if intensity > 0 else ""

        # Resolution
        self._check_resolution(npc_state, info, gs)

        # Build dialogue
        label = EMOTION_LABELS.get(category, category)
        lines = [f"You chose {side}ness → {action_text}"]
        if reaction:
            sign = '+' if new_state > 0 else ''
            lines.append(f"{name} ({label} {sign}{new_state}): {reaction}")
        if npc_state.resolved:
            lines.append(f"[{name} resolved: {npc_state.resolution}]")
            if gs.all_npcs_resolved():
                lines.append("All NPCs resolved — the exit is unlocked!")

        self.npc_dialogue = "\n".join(lines)
        self.npc_dialogue_time = 300

    @staticmethod
    def _check_resolution(npc_state: NPCState, info: dict, gs):
        """Mark NPC resolved if they hit a threshold."""
        es = npc_state.emotional_state
        if es == info["win_threshold"]:
            npc_state.resolved = True
            npc_state.resolution = f"{info['win_direction']}_success"
        elif es == info["fail_threshold"]:
            other = "kind" if info["win_direction"] == "cruel" else "cruel"
            npc_state.resolved = True
            npc_state.resolution = f"{other}_fail"

    # ------------------------------------------------------------------
    # Potions
    # ------------------------------------------------------------------

    def _use_healing_potion(self):
        gs = self.game_state
        if gs.healing_potions <= 0:
            self._show_message("No healing potions!")
            return
        gs.healing_potions -= 1
        heal = gs.rng.randint(5, 15)
        gs.hp = min(gs.max_hp, gs.hp + heal)
        self._show_message(f"Healed +{heal} HP")

    def _use_vision_potion(self):
        gs = self.game_state
        if gs.vision_potions <= 0:
            self._show_message("No vision potions!")
            return
        gs.vision_potions -= 1
        if gs.clear_fog_nearest_cluster():
            self._show_message("Vision potion! Revealed nearby area.")
        else:
            self._show_message("All areas already revealed.")

    def _use_will_potion(self):
        gs = self.game_state
        if gs.will_potions <= 0:
            self._show_message("No will potions!")
            return
        gs.will_potions -= 1
        gs.will = min(gs.max_will, gs.will + 3)
        self._show_message(f"Will restored! Will: {gs.will}/{gs.max_will}")

    def _show_message(self, text: str):
        self.message_text = text
        self.message_time = self.message_duration

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self):
        dt = self.clock.get_time()       # ms
        dt_s = dt / 1000.0               # seconds

        # Smooth per-frame movement
        self._update_movement(dt_s)

        # Mobile NPC AI
        gs = self.game_state
        if not gs.is_dead and not gs.is_complete:
            update_mobile_npcs(
                gs.mobile_npcs, self.maze,
                self.player_row, self.player_col, dt_s,
            )
            # Check if Brian caught the player (auto-damage on contact)
            for npc in gs.mobile_npcs:
                if npc.npc_id == "brian_wererat" and not npc.resolved and npc.active:
                    npc.bite_cooldown = max(0.0, npc.bite_cooldown - dt_s)
                    if npc.manhattan_to(self.player_row, self.player_col) < 0.8 and npc.bite_cooldown <= 0:
                        gs.hp = max(0, gs.hp - 1)
                        npc.bite_cooldown = 3.0
                        self._show_message("Brian bites you! -1 HP")

        # Animation
        self.animator.is_moving = bool(self.keys_held & self._ALL_DIR_KEYS)
        self.animator.update(dt)

        if self.message_time > 0:
            self.message_time -= 1
        if self.npc_dialogue_time > 0:
            self.npc_dialogue_time -= 1
            if self.npc_dialogue_time == 0:
                self.npc_dialogue = None

        gs = self.game_state
        if not self.dead and gs.hp <= 0:
            gs.is_dead = True
            self.dead = True
            self.death_fade_time = 0
            self.death_drip_time = 0

        if self.dead:
            if self.death_fade_time < self.death_fade_duration:
                self.death_fade_time += 1
            elif self.death_drip_time < self.death_drip_duration:
                self.death_drip_time += 1

        self.clock.tick(60)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self):
        self.screen.fill((0, 0, 0))

        TILE_W = self.tile_w
        TILE_H = self.tile_h
        gs = self.game_state

        # Camera centers on hero (uses smooth float position)
        hero_col = self.player_col
        hero_row = self.player_row
        hero_iso_x = (hero_col - hero_row) * (TILE_W / 2)
        hero_iso_y = (hero_col + hero_row) * (TILE_H / 2)
        self.camera_x = self.screen_width / 2 - hero_iso_x
        self.camera_y = self.screen_height / 2 - hero_iso_y

        tile_type_to_asset = {
            'floor': 'floor_tile_s.png',
            'n': 'n_corner_s.png', 'e': 'e_corner_s.png',
            's': 's_corner_s.png', 'w': 'w_corner_s.png',
            'ne_wall': 'ne_wall_s.png', 'se_wall': 'se_wall_s.png',
            'sw_wall': 'sw_wall_s.png', 'nw_wall': 'nw_wall_s.png',
            'ne_hall': 'ne_hall_s.png', 'nw_hall': 'nw_hall_s.png',
            'ne_dead': 'ne_dead_s.png', 'se_dead': 'se_dead_s.png',
            'sw_dead': 'sw_dead_s.png', 'nw_dead': 'nw_dead_s.png',
        }

        doors_to_draw = []

        # Tile pass
        for col, row, tile_type in self._sorted_tiles:
            sx = (col - row) * (TILE_W // 2) + self.camera_x
            sy = (col + row) * (TILE_H // 2) + self.camera_y

            asset_key = tile_type_to_asset.get(tile_type, 'floor_tile_s.png')
            asset = self._get_asset(asset_key)
            if asset:
                aw, ah = asset.get_width(), asset.get_height()
                self.screen.blit(asset, (int(sx - aw // 2), int(sy - ah)))

            pos = Position(row, col)
            if not gs.is_fogged(pos):
                try:
                    cell = self.maze.cell(pos)
                except KeyError:
                    cell = None

                # Pit
                if cell and cell.has_pit and pos not in gs.triggered_pits:
                    pit_a = self._get_asset('pit.png')
                    if pit_a:
                        self.screen.blit(pit_a, (int(sx - pit_a.get_width() // 2), int(sy - pit_a.get_height())))

                # Potions
                if cell and cell.has_healing_potion and pos not in gs.consumed_potions:
                    pa = self._get_asset('potion_h_s.png')
                    if pa:
                        self.screen.blit(pa, (int(sx - pa.get_width() // 2), int(sy - pa.get_height())))
                if cell and cell.has_vision_potion and pos not in gs.consumed_potions:
                    pa = self._get_asset('potion_t_s.png')
                    if pa:
                        self.screen.blit(pa, (int(sx - pa.get_width() // 2), int(sy - pa.get_height())))

                # NPC marker (colored circle)
                if cell and cell.npc_id and cell.npc_id in NPC_REGISTRY:
                    npc_state = gs.npc_states.get(cell.npc_id)
                    if npc_state and not npc_state.resolved:
                        color = (100, 200, 255)  # blue for unresolved
                    else:
                        color = (100, 255, 100)  # green for resolved
                    pygame.draw.circle(
                        self.screen, color,
                        (int(sx), int(sy - TILE_H // 2)),
                        10,
                    )

                # Entrance door
                if cell and cell.kind == CellKind.START:
                    door = self._get_asset('nw_door_o_s.png')
                    if door:
                        dx = int(sx - door.get_width() // 2)
                        dy = int(sy - door.get_height())
                        doors_to_draw.append((door, dx, dy))

                # Exit door
                if cell and cell.kind == CellKind.EXIT:
                    key = 'nw_door_o_s.png' if gs.all_npcs_resolved() else 'nw_door_c_s.png'
                    door = self._get_asset(key)
                    if door:
                        dx = int(sx - door.get_width() // 2)
                        dy = int(sy - door.get_height())
                        doors_to_draw.append((door, dx, dy))

        # Mobile NPCs — drawn at their smooth float positions
        for npc in gs.mobile_npcs:
            if npc.resolved:
                continue
            npc_pos = Position(int(npc.float_row), int(npc.float_col))
            if gs.is_fogged(npc_pos):
                continue  # hidden in fog
            nx = (npc.float_col - npc.float_row) * (TILE_W / 2) + self.camera_x
            ny = (npc.float_col + npc.float_row) * (TILE_H / 2) + self.camera_y
            # Bob animation for floating shoe
            bob_offset = 0
            if npc.shape == "circle":
                bob_offset = int(math.sin(npc.bob_phase) * 6)
            draw_y = int(ny - TILE_H // 2) + bob_offset
            if npc.shape == "diamond":
                # Red diamond for Brian
                size = 10
                pts = [
                    (int(nx), draw_y - size),
                    (int(nx) + size, draw_y),
                    (int(nx), draw_y + size),
                    (int(nx) - size, draw_y),
                ]
                pygame.draw.polygon(self.screen, npc.color, pts)
                pygame.draw.polygon(self.screen, (255, 255, 255), pts, 2)
            else:
                # Purple circle for Floating Shoe
                pygame.draw.circle(self.screen, npc.color, (int(nx), draw_y), 8)
                pygame.draw.circle(self.screen, (255, 255, 255), (int(nx), draw_y), 8, 2)

        # Hero sprite (animated) — positioned from smooth float coords
        sx = (hero_col - hero_row) * (TILE_W / 2) + self.camera_x
        sy = (hero_col + hero_row) * (TILE_H / 2) + self.camera_y
        hero_frame = self.animator.get_scaled_frame(self.debug_scale)
        aw, ah = hero_frame.get_width(), hero_frame.get_height()
        self.screen.blit(hero_frame, (int(sx - aw // 2), int(sy - ah)))

        # Overlay doors
        for surf, dx, dy in doors_to_draw:
            self.screen.blit(surf, (dx, dy))

        # Fog pass
        for col, row, _tt in self._sorted_tiles:
            pos = Position(row, col)
            if not gs.is_fogged(pos):
                continue
            sx = (col - row) * (TILE_W // 2) + self.camera_x
            sy = (col + row) * (TILE_H // 2) + self.camera_y

            # Neighbour fog checks
            n_clear = not gs.is_fogged(Position(row - 1, col))
            s_clear = not gs.is_fogged(Position(row + 1, col))
            w_clear = not gs.is_fogged(Position(row, col - 1))
            e_clear = not gs.is_fogged(Position(row, col + 1))

            clear_count = sum([n_clear, e_clear, s_clear, w_clear])
            if clear_count == 0:
                fog_key = 'fog_c.png'
            elif clear_count == 2:
                if n_clear and e_clear:
                    fog_key = 'fog_e.png'
                elif e_clear and s_clear:
                    fog_key = 'fog_s.png'
                elif s_clear and w_clear:
                    fog_key = 'fog_w.png'
                elif w_clear and n_clear:
                    fog_key = 'fog_n.png'
                else:
                    fog_key = 'fog_c.png'
            elif clear_count == 1:
                if n_clear:
                    fog_key = 'fog_ne.png'
                elif e_clear:
                    fog_key = 'fog_se.png'
                elif s_clear:
                    fog_key = 'fog_sw.png'
                elif w_clear:
                    fog_key = 'fog_nw.png'
                else:
                    fog_key = 'fog_c.png'
            else:
                fog_key = 'fog_c.png'

            fog = self._get_asset(fog_key)
            if fog:
                self.screen.blit(fog, (int(sx - fog.get_width() // 2), int(sy - fog.get_height())))

        # UI overlays — HUD panel (minimap, bars, portrait)
        self.ui_panel.draw(
            self.screen, gs,
            self.player_row, self.player_col,
            self.maze, NPC_REGISTRY,
        )
        self._draw_controls()

        if self.message_time > 0 and self.message_text:
            self._draw_message()

        if self.npc_dialogue:
            self._draw_npc_dialogue()

        if self.won:
            self._draw_win_screen()

        if self.dead:
            self._draw_death_screen()

        pygame.display.flip()

    # ------------------------------------------------------------------
    # UI drawing helpers
    # ------------------------------------------------------------------

    def _draw_controls(self):
        gs = self.game_state
        font = pygame.font.Font(None, 24)
        nearby_npc = self._nearest_npc_id_in_range(radius=4)
        npc_lines = []
        if nearby_npc and nearby_npc in NPC_REGISTRY:
            npc_state = gs.npc_states.get(nearby_npc)
            if npc_state and not npc_state.resolved:
                npc_lines = [
                    f"K - Be kind to {NPC_REGISTRY[nearby_npc]['name']}",
                    f"C - Be cruel to {NPC_REGISTRY[nearby_npc]['name']}",
                ]
        # Mobile NPC controls
        mobile = nearest_mobile_npc_in_range(
            gs.mobile_npcs, self.player_row, self.player_col, 2.0,
        )
        if mobile:
            npc_lines = [
                f"K - Be kind to {mobile.name}",
                f"C - Be cruel to {mobile.name}",
            ]
        lines = [
            "Numpad 1-9 / Arrows — Move",
            f"H - Healing potion ({gs.healing_potions})",
            f"V - Vision potion ({gs.vision_potions})",
            f"W - Will potion ({gs.will_potions})",
        ] + npc_lines

        padding = 6
        line_height = font.get_height() + 2
        box_w = max(font.size(l)[0] for l in lines) + padding * 2
        box_h = line_height * len(lines) + padding * 2
        # Position below the minimap
        bx = 10
        by = self.ui_panel.MINIMAP_SIZE + self.ui_panel.MINIMAP_MARGIN + 10

        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        self.screen.blit(panel, (bx, by))
        for i, line in enumerate(lines):
            txt = font.render(line, True, (255, 255, 255))
            self.screen.blit(txt, (bx + padding, by + padding + i * line_height))

    def _draw_message(self):
        font = pygame.font.Font(None, 48)
        text = font.render(self.message_text, True, (255, 215, 0))
        rect = text.get_rect(center=(self.screen_width // 2, self.screen_height // 2))
        pad = 20
        box = rect.inflate(pad * 2, pad * 2)
        panel = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 200))
        self.screen.blit(panel, box)
        self.screen.blit(text, rect)

    def _draw_npc_dialogue(self):
        """Render multi-line NPC dialogue box at the bottom."""
        if not self.npc_dialogue:
            return
        font = pygame.font.Font(None, 28)
        lines = self.npc_dialogue.split("\n")
        line_height = font.get_height() + 4
        pad = 12
        box_w = min(self.screen_width - 40, 800)
        box_h = line_height * len(lines) + pad * 2
        bx = (self.screen_width - box_w) // 2
        by = self.screen_height - box_h - 20

        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 210))
        self.screen.blit(panel, (bx, by))
        for i, line in enumerate(lines):
            txt = font.render(line, True, (220, 220, 255))
            self.screen.blit(txt, (bx + pad, by + pad + i * line_height))

    def _draw_win_screen(self):
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        font_large = pygame.font.Font(None, 120)
        win_text = font_large.render("YOU WIN!", True, (255, 215, 0))
        wr = win_text.get_rect(center=(self.screen_width // 2, self.screen_height // 2 - 50))
        self.screen.blit(win_text, wr)

        font_sm = pygame.font.Font(None, 32)
        gs = self.game_state
        info = font_sm.render(
            f"Moves: {gs.move_count}  HP: {gs.hp}/{gs.max_hp}",
            True, (200, 200, 200),
        )
        ir = info.get_rect(center=(self.screen_width // 2, self.screen_height // 2 + 40))
        self.screen.blit(info, ir)

        inst = font_sm.render("Close the window to exit", True, (200, 200, 200))
        ir2 = inst.get_rect(center=(self.screen_width // 2, self.screen_height // 2 + 80))
        self.screen.blit(inst, ir2)

    def _draw_death_screen(self):
        if self.death_fade_time < self.death_fade_duration:
            alpha = int(255 * (self.death_fade_time / self.death_fade_duration))
            fade = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
            fade.fill((0, 0, 0, alpha))
            self.screen.blit(fade, (0, 0))
        else:
            self.screen.fill((0, 0, 0))
            if self.death_drip_time > 0:
                font_large = pygame.font.Font(None, 200)
                base = "YOU DIED"
                progress = min(1.0, self.death_drip_time / self.death_drip_duration)

                main = font_large.render(base, True, (200, 0, 0))
                mr = main.get_rect(center=(self.screen_width // 2, self.screen_height // 2 - 100))
                self.screen.blit(main, mr)

                cw = mr.width // len(base)
                for i, ch in enumerate(base):
                    if ch == ' ':
                        continue
                    drip_len = int(100 * progress * (0.8 + 0.4 * ((i * 37) % 100) / 100))
                    dx = mr.left + i * cw + cw // 2
                    dy = mr.bottom
                    for d in range(3):
                        seg = int(drip_len * (1.0 - d * 0.2))
                        if seg > 5:
                            c = (150 - d * 30, 0, 0)
                            pygame.draw.line(self.screen, c, (dx + d * 3 - 3, dy), (dx + d * 3 - 3, dy + seg), 4)

                if self.death_drip_time >= self.death_drip_duration:
                    font_btn = pygame.font.Font(None, 60)
                    btn_txt = font_btn.render("Try Again?", True, (255, 255, 255))
                    br = btn_txt.get_rect(center=(self.screen_width // 2, self.screen_height // 2 + 150))
                    mp = pygame.mouse.get_pos()
                    bg = br.inflate(40, 20)
                    hover = bg.collidepoint(mp)
                    pygame.draw.rect(self.screen, (80, 80, 80) if hover else (50, 50, 50), bg, border_radius=10)
                    pygame.draw.rect(self.screen, (200, 200, 200), bg, 3, border_radius=10)
                    self.screen.blit(btn_txt, br)
                    self.try_again_button = bg
                else:
                    self.try_again_button = None

    # ------------------------------------------------------------------
    # Restart
    # ------------------------------------------------------------------

    def restart_game(self):
        from maze import build_dungeon_maze
        self.dead = False
        self.death_fade_time = 0
        self.death_drip_time = 0
        self.try_again_button = None
        self.won = False
        self.message_text = None
        self.message_time = 0
        self.npc_dialogue = None
        self.npc_dialogue_time = 0

        new_seed = self.seed + 1
        self.seed = new_seed
        self.maze = build_dungeon_maze(seed=new_seed)
        self.game_state = GameState(self.maze, new_seed)
        self._sorted_tiles = self._build_sorted_tile_list()
        self.animator.reset()
        start = self.game_state.pos
        self.player_row = start.row + 0.5
        self.player_col = start.col + 0.5
        self.keys_held.clear()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        while self.running:
            self.handle_input()
            self.update()
            self.render()
        pygame.quit()
        sys.exit()

    def try_move(self, arrow: str) -> bool:
        """Test-friendly one-step movement using 'up/down/left/right'."""
        mapping = {
            "up": Direction.N,
            "down": Direction.S,
            "left": Direction.W,
            "right": Direction.E,
        }

        direction = mapping.get(str(arrow).lower())
        if direction is None:
            return False

        next_pos = self.maze.next_pos(self.game_state.pos, direction)
        if next_pos is None:
            return False

        self.game_state.pos = next_pos
        self.game_state.move_count += 1
        self.game_state._visit(next_pos)

        # Keep render coordinates synced with tile position
        self.player_row = next_pos.row + 0.5
        self.player_col = next_pos.col + 0.5

        # Trigger cell effects
        self._on_enter_cell(next_pos)
        return True

if __name__ == '__main__':
    from maze import build_dungeon_maze
    seed = random.randint(0, 999999)
    print(f"Generating dungeon (seed={seed})...")
    maze = build_dungeon_maze(seed=seed)
    print(f"Maze: {maze.maze_id}, {len(maze.all_cells())} floor cells")
    game = Game(maze=maze, seed=seed)
    game.run()
