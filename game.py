"""
game.py — Pygame Isometric Dungeon Game (Presentation Layer)

Integrates maze.py topology with isometric rendering, NPC emotion system,
and fog of war.  Win condition: resolve both NPCs to unlock the exit.

Domain state lives in game_state.py (GameState, NPC_REGISTRY).
"""
import math
import json
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
)
from game_state import GameState, NPC_REGISTRY
from local_settings import load_local_settings


LOCAL_SETTINGS = load_local_settings()


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


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
    PLAYER_SPEED = LOCAL_SETTINGS.character_speed_tiles_per_second
    TARGET_FPS = max(1, LOCAL_SETTINGS.target_fps)
    BASE_ANIMATION_FPS = max(1, LOCAL_SETTINGS.animation_fps)
    TILE_MARGIN  = 0.05  # stop this far from a blocked edge
    NEG_AXIS_COLLISION_BUFFER = 0.16  # extra stop buffer for NE/NW-side contacts
    FOG_OVERLAP_PX = 2

    # Collision probe offset in tile-space.
    # Keep neutral by default so render anchor and collision sample match.
    COLLISION_PROBE_ROW_OFFSET = 0.0
    COLLISION_PROBE_COL_OFFSET = 0.0

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

        # Zoom — map_scale sizes dungeon tiles/fog; debug_scale sizes the hero sprite
        self.debug_scale = max(0.25, LOCAL_SETTINGS.debug_scale)
        self.map_scale = 3.0
        self.tile_w = int(128 * self.map_scale)
        self.tile_h = int(75 * self.map_scale)
        self._scaled_assets_cache: dict = {}
        self._fog_overlap_cache: dict[tuple[str, int, int], pygame.Surface] = {}
        self._fog_exact_cache: dict[tuple[str, int, int], pygame.Surface] = {}

        # Input
        self.keys_held: set[str] = set()

        # Messages / NPC dialogue
        self.message_text: Optional[str] = None
        self.message_time: int = 0
        self.message_duration: int = int(self.TARGET_FPS * 3)
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
        assets_dir = Path(get_resource_path('assets'))
        if not assets_dir.exists():
            assets_dir = Path(__file__).parent / 'assets'

        candidate_sheets = [
            assets_dir / 'witch_sprite_sheet.png',
            assets_dir / 'sprte sheet isometric silhouette.png',
        ]
        sheet_path = next((p for p in candidate_sheets if p.exists()), None)
        if sheet_path is None:
            raise FileNotFoundError(
                "Missing sprite sheet. Expected one of: "
                "assets/witch_sprite_sheet.png or "
                "assets/sprte sheet isometric silhouette.png"
            )
        self.animator = SpriteAnimator(str(sheet_path), fps=self.BASE_ANIMATION_FPS)

        # Pre-build sorted tile list for rendering
        self._sorted_tiles = self._build_sorted_tile_list()

        # ---- Debug mode ----
        self.debug_mode: bool = False
        self._dbg_player_row: float = 0.5
        self._dbg_player_col: float = 0.5
        self._dbg_collision: bool = False
        self._dbg_zoom_pct: int = int(self.map_scale * 100)
        self._dbg_anim_speed_pct: int = 100
        self._dbg_move_speed_pct: int = 100
        self._dbg_probe_tile: tuple[int, int] = (11, 2)
        self._dbg_btn_rects: dict[str, pygame.Rect] = {}
        self._dbg_last_probe: Optional[dict[str, object]] = None
        self._dbg_font_sm = pygame.font.Font(None, 16)
        self._dbg_font_md = pygame.font.Font(None, 26)
        self._dbg_font_lg = pygame.font.Font(None, 30)
        self._dbg_screen: int = 0  # 0 = general debug, 1 = fog placement
        self._dbg_fog_grid_size: int = 10
        self._dbg_fog_assignments: dict[tuple[int, int], list[int]] = {}
        self._dbg_fog_hover_tile: Optional[tuple[int, int]] = None
        self._dbg_fog_output_button: Optional[pygame.Rect] = None
        self._dbg_fog_last_output_count: int = 0
        self._dbg_fog_zoom_pct: int = 100

        # Numpad layout: 7/8/9 on top row, 4/5/6 middle, 1/2/3 bottom.
        self._dbg_fog_num_to_key: dict[int, str] = {
            1: 'fog_sw.png',
            2: 'fog_s.png',
            3: 'fog_se.png',
            4: 'fog_w.png',
            5: 'fog_c.png',
            6: 'fog_e.png',
            7: 'fog_nw.png',
            8: 'fog_n.png',
            9: 'fog_ne.png',
        }

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
        # Map assets (floors, walls, fog, doors, etc.) render at map_scale;
        # everything else (potions, hero statics, NPCs) stays at 1:1.
        key_lower = key.lower()
        _MAP_KEYS = ('hall', 'door', 'corner', 'dead', 'wall',
                     'pillar', 'pit', 'floor', 'fog')
        scale = self.map_scale if any(k in key_lower for k in _MAP_KEYS) else 1.0
        if scale == 1.0:
            return surf
        cached = self._scaled_assets_cache.get(key)
        if cached:
            return cached
        w = max(1, int(surf.get_width() * scale))
        h = max(1, int(surf.get_height() * scale))
        scaled = pygame.transform.smoothscale(surf, (w, h))
        self._scaled_assets_cache[key] = scaled
        return scaled

    def _get_fog_asset(self, key: str, overlap_px: Optional[int] = None):
        src = self.assets.get(key)
        if src is None:
            return None
        if overlap_px is None:
            overlap_px = self.FOG_OVERLAP_PX
        overlap = max(0, int(overlap_px))
        base_w = max(1, int(round(src.get_width() * self.map_scale)))
        base_h = max(1, int(round(src.get_height() * self.map_scale)))
        target_w = base_w + overlap * 2
        target_h = base_h + overlap * 2
        cache_key = (f"{key}:{overlap}", target_w, target_h)
        cached = self._fog_overlap_cache.get(cache_key)
        if cached is not None:
            return cached
        # Use nearest-neighbor scaling for fog to avoid semi-transparent seam artifacts.
        expanded = pygame.transform.scale(src, (target_w, target_h))
        self._fog_overlap_cache[cache_key] = expanded
        return expanded

    def _get_fog_asset_exact(self, key: str):
        """Fog sprite scaled exactly like debugger tiles (no overlap expansion)."""
        src = self.assets.get(key)
        if src is None:
            return None
        target_w = max(1, int(round(src.get_width() * self.map_scale)))
        target_h = max(1, int(round(src.get_height() * self.map_scale)))
        cache_key = (key, target_w, target_h)
        cached = self._fog_exact_cache.get(cache_key)
        if cached is not None:
            return cached
        scaled = pygame.transform.scale(src, (target_w, target_h))
        self._fog_exact_cache[cache_key] = scaled
        return scaled

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.debug_mode:
                    if self._dbg_screen == 0:
                        for label, rect in self._dbg_btn_rects.items():
                            if rect.collidepoint(event.pos):
                                self._dbg_handle_button(label)
                                break
                    else:
                        if self._dbg_fog_output_button and self._dbg_fog_output_button.collidepoint(event.pos):
                            self._dbg_emit_fog_output()
                elif self.dead and self.try_again_button:
                    if self.try_again_button.collidepoint(event.pos):
                        self.restart_game()
            elif event.type == pygame.KEYDOWN:
                if self.debug_mode:
                    if event.key == pygame.K_TAB:
                        self._dbg_screen = 1 - self._dbg_screen
                        self.keys_held.clear()
                        continue
                    if self._dbg_screen == 1:
                        num = self._dbg_numpad_digit(event.key)
                        if num is not None:
                            self._dbg_apply_fog_number(num)
                            continue
                        if event.key in {pygame.K_DELETE, pygame.K_BACKSPACE}:
                            self._dbg_remove_hover_fog()
                            continue
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
                elif event.key == pygame.K_d:
                    self.debug_mode = not self.debug_mode
                    self._dbg_screen = 0
                    self._dbg_player_row = 0.5
                    self._dbg_player_col = 0.5
                    self.keys_held.clear()
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

    def _to_collision_probe(self, row: float, col: float) -> tuple[float, float]:
        """Convert render anchor coordinates to collision probe coordinates."""
        return (
            row + self.COLLISION_PROBE_ROW_OFFSET,
            col + self.COLLISION_PROBE_COL_OFFSET,
        )

    def _from_collision_probe(self, row: float, col: float) -> tuple[float, float]:
        """Convert collision probe coordinates back to render anchor coordinates."""
        return (
            row - self.COLLISION_PROBE_ROW_OFFSET,
            col - self.COLLISION_PROBE_COL_OFFSET,
        )

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

        # If pushing toward a blocked negative-side boundary, hold at the
        # buffered stop line immediately to prevent shake/oscillation.
        if delta < 0 and self.NEG_AXIS_COLLISION_BUFFER > 0.0:
            if axis_is_row:
                from_r, from_c = old_tile, math.floor(other_axis)
                to_r, to_c = old_tile - 1, from_c
            else:
                from_r, from_c = math.floor(other_axis), old_tile
                to_r, to_c = from_r, old_tile - 1

            blocked_neg = not (
                self._is_floor(to_r, to_c)
                and self._can_pass(from_r, from_c, to_r, to_c)
            )
            stop_line = float(old_tile) + self.NEG_AXIS_COLLISION_BUFFER + 1e-9
            if blocked_neg and cur <= stop_line:
                return stop_line

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

        # Blocked — hold exactly at the tile boundary.
        # Using 1e-9 offset keeps floor() on the safe side, prevents
        # the margin > step oscillation that caused screen vibration,
        # and makes NE/NW and SW/SE stop symmetrically at the wall.
        if delta > 0:
            return float(new_tile) - 1e-9   # just inside current tile, upper edge
        else:
            # Add a small inward buffer for negative-axis movement (NE/NW side).
            return float(new_tile + 1) + self.NEG_AXIS_COLLISION_BUFFER + 1e-9

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
            # Left/right on screen (pure E or W) → 2.3× base fps
            # All other directions (N/S straight + all diagonals) → 3× base fps
            self.animator.fps = int(self.BASE_ANIMATION_FPS * (2.3 if facing in ('W', 'E') else 3.0))

        # Apply movement (axis-separated for wall sliding) in collision-probe space
        step = self.PLAYER_SPEED * dt_s
        probe_row, probe_col = self._to_collision_probe(self.player_row, self.player_col)
        probe_col = self._try_axis(
            probe_col, vc * step, probe_row, axis_is_row=False)
        probe_row = self._try_axis(
            probe_row, vr * step, probe_col, axis_is_row=True)
        self.player_row, self.player_col = self._from_collision_probe(probe_row, probe_col)

        # Detect tile change from collision probe → fire game events
        new_tile = Position(math.floor(probe_row), math.floor(probe_col))
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

        self.clock.tick(self.TARGET_FPS)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self):
        self.screen.fill((0, 0, 0))

        TILE_W = self.tile_w
        TILE_H = self.tile_h
        dungeon_y_offset = TILE_H  # visual-only shift: move dungeon down 1 tile
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
            sy = (col + row) * (TILE_H // 2) + self.camera_y + dungeon_y_offset

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
            ny = (npc.float_col + npc.float_row) * (TILE_H / 2) + self.camera_y + dungeon_y_offset
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

        # Fog pass (debugger-style): draw fog_c at fogged cells, then border overlays
        # on neighboring non-fog cells around each fog_c source tile.
        fog_layers_by_pos: dict[Position, list[str]] = {}

        def _add_layer(pos: Position, fog_key: str):
            layers = fog_layers_by_pos.setdefault(pos, [])
            if fog_key not in layers:
                layers.append(fog_key)

        border_map = [
            ((-1, 0), 'fog_ne.png'),
            ((0, 1), 'fog_se.png'),
            ((1, 0), 'fog_sw.png'),
            ((0, -1), 'fog_nw.png'),
            ((-1, -1), 'fog_n.png'),
            ((-1, 1), 'fog_e.png'),
            ((1, 1), 'fog_s.png'),
            ((1, -1), 'fog_w.png'),
        ]

        for fog_pos, fogged in gs.fog.items():
            if not fogged:
                continue
            _add_layer(fog_pos, 'fog_c.png')
            for (dr, dc), fog_key in border_map:
                npos = Position(fog_pos.row + dr, fog_pos.col + dc)
                if npos not in gs.fog:
                    continue
                if gs.is_fogged(npos):
                    continue
                _add_layer(npos, fog_key)

        for col, row, _tt in self._sorted_tiles:
            pos = Position(row, col)
            fog_layers = fog_layers_by_pos.get(pos)
            if not fog_layers:
                continue
            sx = (col - row) * (TILE_W // 2) + self.camera_x
            sy = (col + row) * (TILE_H // 2) + self.camera_y + dungeon_y_offset
            for fog_key in fog_layers:
                fog = self._get_fog_asset_exact(fog_key)
                if fog:
                    self.screen.blit(fog, (round(sx - fog.get_width() / 2), round(sy - fog.get_height())))

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

        if LOCAL_SETTINGS.debug_overlay_enabled:
            lines += [
                f"Debug scale: {self.debug_scale:.2f}",
                f"Target FPS: {self.TARGET_FPS}",
                f"Anim FPS: {self.BASE_ANIMATION_FPS}",
                f"Speed: {self.PLAYER_SPEED:.2f} tiles/s",
                f"Dungeon size: {self.maze.width}x{self.maze.height}",
            ]

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
        self.maze = build_dungeon_maze(
            seed=new_seed,
            width=LOCAL_SETTINGS.dungeon_width,
            height=LOCAL_SETTINGS.dungeon_height,
            max_rooms=LOCAL_SETTINGS.dungeon_max_rooms,
            min_room_size=LOCAL_SETTINGS.dungeon_min_room_size,
            max_room_size=LOCAL_SETTINGS.dungeon_max_room_size,
        )
        self.game_state = GameState(self.maze, new_seed)
        self._sorted_tiles = self._build_sorted_tile_list()
        self.animator.reset()
        start = self.game_state.pos
        self.player_row = start.row + 0.5
        self.player_col = start.col + 0.5
        self.keys_held.clear()

    # ------------------------------------------------------------------
    # Debug mode
    # ------------------------------------------------------------------

    def _dbg_spiral_positions(self) -> list[tuple[int, int]]:
        """Return (row, col) 0-indexed spiral starting at (4,4) — user's r5c5."""
        positions: list[tuple[int, int]] = []
        r, c = 4, 4
        positions.append((r, c))
        step = 1
        dr_seq = [0, 1, 0, -1]
        dc_seq = [1, 0, -1, 0]
        dir_idx = 0
        while len(positions) < 100:
            for _ in range(2):
                dr, dc = dr_seq[dir_idx % 4], dc_seq[dir_idx % 4]
                for _ in range(step):
                    r += dr
                    c += dc
                    positions.append((r, c))
                    if len(positions) >= 100:
                        return positions
                dir_idx += 1
            step += 1
        return positions

    def _dbg_handle_button(self, label: str):
        step = 10
        if label == 'Collision':
            self._dbg_collision = not self._dbg_collision
        elif label == 'Zoom+':
            self._dbg_zoom_pct = min(300, self._dbg_zoom_pct + step)
        elif label == 'Zoom-':
            self._dbg_zoom_pct = max(30, self._dbg_zoom_pct - step)
        elif label == 'Run+':
            self._dbg_anim_speed_pct = min(400, self._dbg_anim_speed_pct + step)
        elif label == 'Run-':
            self._dbg_anim_speed_pct = max(10, self._dbg_anim_speed_pct - step)
        elif label == 'Move+':
            self._dbg_move_speed_pct = min(400, self._dbg_move_speed_pct + step)
        elif label == 'Move-':
            self._dbg_move_speed_pct = max(10, self._dbg_move_speed_pct - step)
        elif label in {'NE', 'NW', 'SE', 'SW', 'Center'}:
            tile_row = math.floor(self._dbg_player_row)
            tile_col = math.floor(self._dbg_player_col)
            self._dbg_last_probe = {
                'label': label,
                'row': round(self._dbg_player_row, 4),
                'col': round(self._dbg_player_col, 4),
                'tile_row': tile_row + 1,
                'tile_col': tile_col + 1,
                'offset_row': round(self._dbg_player_row - (tile_row + 0.5), 4),
                'offset_col': round(self._dbg_player_col - (tile_col + 0.5), 4),
            }
            print(
                "DBG_PROBE"
                f" label={self._dbg_last_probe['label']}"
                f" row={self._dbg_last_probe['row']}"
                f" col={self._dbg_last_probe['col']}"
                f" tile_r={self._dbg_last_probe['tile_row']}"
                f" tile_c={self._dbg_last_probe['tile_col']}"
                f" offset_row={self._dbg_last_probe['offset_row']}"
                f" offset_col={self._dbg_last_probe['offset_col']}",
                flush=True,
            )

    def _dbg_update(self, dt_s: float):
        """Movement and animation update for debug mode."""
        vr, vc = 0.0, 0.0
        for key in self.keys_held:
            v = self._VELOCITY_MAP.get(key)
            if v:
                vr += v[0]
                vc += v[1]

        is_moving = (vr != 0.0 or vc != 0.0)
        self.animator.is_moving = is_moving

        if is_moving:
            mag = math.hypot(vr, vc)
            vr /= mag
            vc /= mag
            sr = -1 if vr < 0 else (1 if vr > 0 else 0)
            sc = -1 if vc < 0 else (1 if vc > 0 else 0)
            facing = self._SIGN_TO_FACING.get((sr, sc))
            if facing:
                self.animator.set_direction(facing)

            speed = self.PLAYER_SPEED * (self._dbg_move_speed_pct / 100.0)
            new_col = self._dbg_player_col + vc * speed * dt_s
            new_row = self._dbg_player_row + vr * speed * dt_s
            max_dbg_row = max(10.5, self._dbg_probe_tile[0] + 0.5)
            max_dbg_col = max(10.5, self._dbg_probe_tile[1] + 0.5)
            if self._dbg_collision:
                new_col = max(self.TILE_MARGIN, min(max_dbg_col - self.TILE_MARGIN, new_col))
                new_row = max(self.TILE_MARGIN, min(max_dbg_row - self.TILE_MARGIN, new_row))
            else:
                new_col = max(-0.5, min(max_dbg_col, new_col))
                new_row = max(-0.5, min(max_dbg_row, new_row))
            self._dbg_player_col = new_col
            self._dbg_player_row = new_row

        target_fps = max(1, int(self.BASE_ANIMATION_FPS * self._dbg_anim_speed_pct / 100))
        self.animator.fps = target_fps
        self.animator.update(dt_s * 1000.0)

    def _dbg_pick_fog_tile(self, mouse_pos: tuple[int, int], to_screen, tile_w: int, tile_h: int) -> Optional[tuple[int, int]]:
        best_tile = None
        best_score = float('inf')
        mx, my = mouse_pos
        for row in range(self._dbg_fog_grid_size):
            for col in range(self._dbg_fog_grid_size):
                cx, cy = to_screen(row, col)
                nx = abs(mx - cx) / max(1.0, tile_w / 2)
                ny = abs(my - cy) / max(1.0, tile_h / 2)
                score = nx + ny
                if score <= 1.0 and score < best_score:
                    best_score = score
                    best_tile = (row, col)
        return best_tile

    def _dbg_apply_fog_number(self, number: int):
        if self._dbg_fog_hover_tile is None:
            return
        if number not in self._dbg_fog_num_to_key:
            return
        stack = self._dbg_fog_assignments.setdefault(self._dbg_fog_hover_tile, [])
        stack.append(number)

    @staticmethod
    def _dbg_numpad_digit(key: int) -> Optional[int]:
        mapping = {
            pygame.K_KP1: 1, pygame.K_KP2: 2, pygame.K_KP3: 3,
            pygame.K_KP4: 4, pygame.K_KP5: 5, pygame.K_KP6: 6,
            pygame.K_KP7: 7, pygame.K_KP8: 8, pygame.K_KP9: 9,
        }
        return mapping.get(key)

    def _dbg_remove_hover_fog(self):
        if self._dbg_fog_hover_tile is None:
            return
        stack = self._dbg_fog_assignments.get(self._dbg_fog_hover_tile)
        if not stack:
            return
        stack.pop()
        if not stack:
            self._dbg_fog_assignments.pop(self._dbg_fog_hover_tile, None)

    def _dbg_emit_fog_output(self):
        entries = []
        for (row, col), numbers in sorted(self._dbg_fog_assignments.items(), key=lambda x: (x[0][0], x[0][1])):
            for layer_index, number in enumerate(numbers):
                fog_key = self._dbg_fog_num_to_key[number]
                entries.append({
                    'row0': row,
                    'col0': col,
                    'row1': row + 1,
                    'col1': col + 1,
                    'layer': layer_index,
                    'tile_number': number,
                    'fog_key': fog_key,
                })

        payload = {
            'grid_size': self._dbg_fog_grid_size,
            'mapping': {str(k): v for k, v in self._dbg_fog_num_to_key.items()},
            'placements': entries,
        }

        print('FOG_DEBUG_OUTPUT_BEGIN', flush=True)
        print(json.dumps(payload, indent=2), flush=True)
        print('FOG_DEBUG_OUTPUT_END', flush=True)
        self._dbg_fog_last_output_count = len(entries)

    def _debug_render_fog(self):
        self.screen.fill((14, 18, 28))

        zoom = self._dbg_fog_zoom_pct / 100.0
        tw = max(16, int(128 * zoom))
        th = max(10, int(75 * zoom))
        grid = self._dbg_fog_grid_size

        center_row = (grid - 1) / 2
        center_col = (grid - 1) / 2
        center_iso_x = (center_col - center_row) * (tw / 2)
        center_iso_y = (center_col + center_row) * (th / 2)
        cam_x = self.screen_width * 0.36 - center_iso_x
        cam_y = self.screen_height * 0.50 - center_iso_y

        def to_screen(row: float, col: float) -> tuple[float, float]:
            return (col - row) * (tw / 2) + cam_x, (col + row) * (th / 2) + cam_y

        self._dbg_fog_hover_tile = self._dbg_pick_fog_tile(pygame.mouse.get_pos(), to_screen, tw, th)

        floor = self.assets.get('floor_tile_s.png')
        floor_scaled_cache: Optional[pygame.Surface] = None
        fog_cache: dict[int, Optional[pygame.Surface]] = {}

        for row in range(grid):
            for col in range(grid):
                sx, sy = to_screen(row, col)

                if floor is not None:
                    if floor_scaled_cache is None:
                        tile_base: pygame.Surface = floor
                        if zoom != 1.0:
                            floor_scaled_cache = pygame.transform.scale(
                                tile_base,
                                (max(1, int(tile_base.get_width() * zoom)),
                                 max(1, int(tile_base.get_height() * zoom))),
                            )
                        else:
                            floor_scaled_cache = tile_base
                    tile_surf = floor_scaled_cache
                    self.screen.blit(tile_surf, (int(sx - tile_surf.get_width() // 2), int(sy - tile_surf.get_height())))

                assigned_stack = self._dbg_fog_assignments.get((row, col), [])
                for assigned in assigned_stack:
                    if assigned not in fog_cache:
                        src_fog = self.assets.get(self._dbg_fog_num_to_key[assigned])
                        if src_fog is None:
                            fog_cache[assigned] = None
                        else:
                            target_w = max(1, int(src_fog.get_width() * zoom))
                            target_h = max(1, int(src_fog.get_height() * zoom))
                            fog_cache[assigned] = pygame.transform.scale(src_fog, (target_w, target_h))
                    fog = fog_cache[assigned]
                    if fog is not None:
                        self.screen.blit(fog, (round(sx - fog.get_width() / 2), round(sy - fog.get_height())))

                if self._dbg_fog_hover_tile == (row, col):
                    top = to_screen(row - 0.5, col)
                    right = to_screen(row, col + 0.5)
                    bottom = to_screen(row + 0.5, col)
                    left = to_screen(row, col - 0.5)
                    points = [(int(p[0]), int(p[1])) for p in (top, right, bottom, left)]
                    pygame.draw.polygon(self.screen, (255, 225, 100), points, 2)

        panel_x = self.screen_width - 320
        panel_y = 16
        panel_w = 300
        panel_h = self.screen_height - 32
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        self.screen.blit(panel, (panel_x, panel_y))

        title = self._dbg_font_lg.render('DEBUG FOG SCREEN', True, (255, 215, 0))
        self.screen.blit(title, (panel_x + 12, panel_y + 10))

        help_lines = [
            'TAB: switch debug screens',
            'D: exit debug mode',
            'Hover a tile, use NUMPAD 1-9',
            'Each press adds another layer',
            'Delete/Backspace removes top layer',
        ]
        text_y = panel_y + 48
        for line in help_lines:
            txt = self._dbg_font_sm.render(line, True, (220, 220, 220))
            self.screen.blit(txt, (panel_x + 12, text_y))
            text_y += 18

        text_y += 6
        legend_numbers = [7, 8, 9, 4, 5, 6, 1, 2, 3]
        for idx, number in enumerate(legend_numbers):
            fog_key = self._dbg_fog_num_to_key[number]
            row_top = text_y + idx * 28
            badge_rect = pygame.Rect(panel_x + 12, row_top, 24, 22)
            pygame.draw.rect(self.screen, (45, 55, 80), badge_rect, border_radius=4)
            pygame.draw.rect(self.screen, (130, 150, 200), badge_rect, 1, border_radius=4)
            num_txt = self._dbg_font_sm.render(str(number), True, (255, 255, 255))
            self.screen.blit(num_txt, num_txt.get_rect(center=badge_rect.center))

            fog_thumb = self.assets.get(fog_key)
            if fog_thumb is not None:
                thumb_h = 20
                thumb_w = max(1, int(fog_thumb.get_width() * (thumb_h / max(1, fog_thumb.get_height()))))
                thumb = pygame.transform.scale(fog_thumb, (thumb_w, thumb_h))
                self.screen.blit(thumb, (panel_x + 44, row_top + 1))

            label = self._dbg_font_sm.render(fog_key.replace('.png', ''), True, (210, 210, 210))
            self.screen.blit(label, (panel_x + 70, row_top + 4))

        output_rect = pygame.Rect(panel_x + 12, panel_y + panel_h - 84, panel_w - 24, 34)
        pygame.draw.rect(self.screen, (35, 90, 35), output_rect, border_radius=6)
        pygame.draw.rect(self.screen, (170, 230, 170), output_rect, 2, border_radius=6)
        output_text = self._dbg_font_md.render('OUTPUT', True, (255, 255, 255))
        self.screen.blit(output_text, output_text.get_rect(center=output_rect.center))
        self._dbg_fog_output_button = output_rect

        placed_tile_count = len(self._dbg_fog_assignments)
        placed_layer_count = sum(len(v) for v in self._dbg_fog_assignments.values())
        placed = self._dbg_font_sm.render(
            f'Tiles used: {placed_tile_count}  Layers: {placed_layer_count}', True, (220, 220, 220)
        )
        self.screen.blit(placed, (panel_x + 12, panel_y + panel_h - 44))

        if self._dbg_fog_hover_tile is not None:
            r, c = self._dbg_fog_hover_tile
            hover_txt = self._dbg_font_sm.render(f'Hover: r{r + 1} c{c + 1}', True, (255, 235, 160))
            self.screen.blit(hover_txt, (panel_x + 12, panel_y + panel_h - 24))

        if self._dbg_fog_last_output_count > 0:
            out_txt = self._dbg_font_sm.render(
                f'Last output placements: {self._dbg_fog_last_output_count}', True, (190, 255, 190)
            )
            self.screen.blit(out_txt, (18, 16))

        pygame.display.flip()

    def _debug_render(self):
        """Render the isometric 10x10 debug grid with all game assets and controls."""
        self.screen.fill((20, 20, 40))

        zoom = self._dbg_zoom_pct / 100.0
        TW = max(16, int(128 * zoom))
        TH = max(10, int(75 * zoom))

        hero_row = self._dbg_player_row
        hero_col = self._dbg_player_col
        hero_iso_x = (hero_col - hero_row) * (TW / 2)
        hero_iso_y = (hero_col + hero_row) * (TH / 2)
        cam_x = self.screen_width / 2 - hero_iso_x
        cam_y = self.screen_height / 2 - hero_iso_y

        def to_screen(r: float, c: float) -> tuple[float, float]:
            return (c - r) * (TW / 2) + cam_x, (c + r) * (TH / 2) + cam_y

        # Grid outlines — 10×10 isometric diamonds
        for row in range(10):
            for col in range(10):
                top    = to_screen(row - 0.5, col)
                right  = to_screen(row,       col + 0.5)
                bottom = to_screen(row + 0.5, col)
                left   = to_screen(row,       col - 0.5)
                pts = [(int(p[0]), int(p[1])) for p in (top, right, bottom, left)]
                pygame.draw.polygon(self.screen, (60, 60, 80), pts, 1)

        # Isolated probe tile, outside the 10x10 grid and non-adjacent to it.
        dbg_r, dbg_c = self._dbg_probe_tile
        dbg_sx, dbg_sy = to_screen(dbg_r, dbg_c)
        dbg_tile = self.assets.get('floor_tile_s.png')
        if dbg_tile is not None:
            if zoom != 1.0:
                dbg_tile = pygame.transform.scale(
                    dbg_tile,
                    (max(1, int(dbg_tile.get_width() * zoom)),
                     max(1, int(dbg_tile.get_height() * zoom))),
                )
            self.screen.blit(
                dbg_tile,
                (int(dbg_sx - dbg_tile.get_width() // 2), int(dbg_sy - dbg_tile.get_height())),
            )
        dbg_label = self._dbg_font_md.render('debug tile', True, (255, 230, 140))
        self.screen.blit(dbg_label, (int(dbg_sx - dbg_label.get_width() // 2), int(dbg_sy + 10)))

        # Build sorted draw list (painter's algorithm: col+row, col, priority)
        # priority 0 = floor tile strip/column, 1 = spiral assets
        draw_items: list[tuple] = []
        for r, c in [(0, 0), (0, 1), (0, 2), (7, 9), (8, 9), (9, 9)]:
            draw_items.append((c + r, c, 0, 'floor', r, c, None))

        sorted_keys = sorted(self.assets.keys())
        spiral = self._dbg_spiral_positions()
        for i, key in enumerate(sorted_keys):
            if i >= len(spiral):
                break
            r, c = spiral[i]
            if 0 <= r < 10 and 0 <= c < 10:
                draw_items.append((c + r, c, 1, 'asset', r, c, key))

        draw_items.sort(key=lambda x: (x[0], x[1], x[2]))

        lbl_font = self._dbg_font_sm
        for _, _, _, kind, row, col, data in draw_items:
            sx, sy = to_screen(row, col)
            surf = self.assets.get('floor_tile_s.png' if kind == 'floor' else data)
            if surf is None:
                continue
            if zoom != 1.0:
                w = max(1, int(surf.get_width() * zoom))
                h = max(1, int(surf.get_height() * zoom))
                surf = pygame.transform.scale(surf, (w, h))
            aw, ah = surf.get_width(), surf.get_height()
            self.screen.blit(surf, (int(sx - aw // 2), int(sy - ah)))
            if kind == 'asset' and data and TW >= 48:
                name = data.replace('_s.png', '').replace('.png', '')
                lbl = lbl_font.render(name, True, (200, 200, 200))
                self.screen.blit(lbl, (int(sx - lbl.get_width() // 2),
                                       int(sy - ah // 2 - 6)))

        # Hero sprite (always at natural 1× scale)
        hsx, hsy = to_screen(hero_row, hero_col)
        frame = self.animator.get_scaled_frame(1.0)
        fw, fh = frame.get_width(), frame.get_height()
        self.screen.blit(frame, (int(hsx - fw // 2), int(hsy - fh)))

        # Right-side control panel
        self._dbg_btn_rects = {}
        px = self.screen_width - 210
        py = 15
        bw, bh = 190, 34
        half = (bw - 8) // 2
        font = self._dbg_font_md
        lg = self._dbg_font_lg

        title = lg.render("DEBUG  [D] to exit", True, (255, 200, 0))
        self.screen.blit(title, (px, py))
        py += 38

        # Collision toggle (full width)
        cr = pygame.Rect(px, py, bw, bh)
        pygame.draw.rect(self.screen,
                         (80, 60, 20) if self._dbg_collision else (40, 40, 60),
                         cr, border_radius=5)
        pygame.draw.rect(self.screen,
                         (255, 220, 0) if self._dbg_collision else (120, 120, 180),
                         cr, 2, border_radius=5)
        cl = "Collision: ON" if self._dbg_collision else "Collision: OFF"
        ct = font.render(cl, True, (255, 255, 255))
        self.screen.blit(ct, ct.get_rect(center=cr.center))
        self._dbg_btn_rects['Collision'] = cr
        py += bh + 8

        # Zoom / Run / Move paired buttons
        for row_labels, val_txt in [
            (('Zoom+', 'Zoom-'), f"Zoom  {self._dbg_zoom_pct}%"),
            (('Run+',  'Run-'),  f"Anim  {self._dbg_anim_speed_pct}%"),
            (('Move+', 'Move-'), f"Move  {self._dbg_move_speed_pct}%"),
        ]:
            for lbl, bx in [(row_labels[0], px), (row_labels[1], px + half + 8)]:
                br = pygame.Rect(bx, py, half, bh)
                pygame.draw.rect(self.screen, (40, 40, 60), br, border_radius=5)
                pygame.draw.rect(self.screen, (120, 120, 180), br, 2, border_radius=5)
                lt = font.render(lbl, True, (255, 255, 255))
                self.screen.blit(lt, lt.get_rect(center=br.center))
                self._dbg_btn_rects[lbl] = br
            py += bh + 4
            vt = font.render(val_txt, True, (180, 180, 255))
            self.screen.blit(vt, (px, py))
            py += 26

        py += 6
        probe_title = font.render('Probe capture', True, (255, 230, 140))
        self.screen.blit(probe_title, (px, py))
        py += 28

        for row_labels in [('NW', 'NE'), ('SW', 'SE')]:
            for lbl, bx in [(row_labels[0], px), (row_labels[1], px + half + 8)]:
                br = pygame.Rect(bx, py, half, bh)
                pygame.draw.rect(self.screen, (55, 45, 30), br, border_radius=5)
                pygame.draw.rect(self.screen, (200, 170, 90), br, 2, border_radius=5)
                lt = font.render(lbl, True, (255, 255, 255))
                self.screen.blit(lt, lt.get_rect(center=br.center))
                self._dbg_btn_rects[lbl] = br
            py += bh + 6

        center_rect = pygame.Rect(px, py, bw, bh)
        pygame.draw.rect(self.screen, (55, 45, 30), center_rect, border_radius=5)
        pygame.draw.rect(self.screen, (200, 170, 90), center_rect, 2, border_radius=5)
        center_text = font.render('Center', True, (255, 255, 255))
        self.screen.blit(center_text, center_text.get_rect(center=center_rect.center))
        self._dbg_btn_rects['Center'] = center_rect
        py += bh + 10

        if self._dbg_last_probe is None:
            info_lines = ['Last probe: none']
        else:
            probe = self._dbg_last_probe
            info_lines = [
                f"Last: {probe['label']}",
                f"Pos row={probe['row']} col={probe['col']}",
                f"Tile r{probe['tile_row']} c{probe['tile_col']}",
                f"Offset row={probe['offset_row']} col={probe['offset_col']}",
            ]
        for line in info_lines:
            txt = self._dbg_font_sm.render(line, True, (220, 220, 220))
            self.screen.blit(txt, (px, py))
            py += 18

        # Player position (1-indexed display)
        py += 8
        tile_r = math.floor(self._dbg_player_row) + 1
        tile_c = math.floor(self._dbg_player_col) + 1
        pt = font.render(f"Pos: r{tile_r} c{tile_c}", True, (200, 200, 255))
        self.screen.blit(pt, (px, py))

        pygame.display.flip()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        while self.running:
            self.handle_input()
            if self.debug_mode:
                dt_s = self.clock.get_time() / 1000.0
                if self._dbg_screen == 0:
                    self._dbg_update(dt_s)
                    self._debug_render()
                else:
                    self.animator.is_moving = False
                    self.animator.update(dt_s * 1000.0)
                    self._debug_render_fog()
                self.clock.tick(self.TARGET_FPS)
            else:
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
    maze = build_dungeon_maze(
        seed=seed,
        width=LOCAL_SETTINGS.dungeon_width,
        height=LOCAL_SETTINGS.dungeon_height,
        max_rooms=LOCAL_SETTINGS.dungeon_max_rooms,
        min_room_size=LOCAL_SETTINGS.dungeon_min_room_size,
        max_room_size=LOCAL_SETTINGS.dungeon_max_room_size,
    )
    print(f"Maze: {maze.maze_id}, {len(maze.all_cells())} floor cells")
    game = Game(maze=maze, seed=seed)
    game.run()
