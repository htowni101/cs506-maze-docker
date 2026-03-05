"""
ui_panel.py — HUD overlay for the isometric dungeon game.

Renders:
  • Minimap (top-left) — visited tiles lit, unvisited hidden, player dot
  • Health bar (red, 10 segments) + Will bar (blue, 10 segments)
  • NPC portrait (bottom-right) — emotion-driven face PNG when within 4 tiles

Design note: NPC art is loaded by *prefix* (e.g. ``"gob"``).  When new NPC
art sets are created, register them in ``NPC_ART_PREFIX`` so the system picks
the right folder of PNGs automatically.  Until then every NPC falls back to
the default ``"gob"`` prefix.
"""
from __future__ import annotations

import math
import os
import pygame
from pathlib import Path
from typing import Optional

from maze import Maze, Position
from npc_data import NPCState


def _resource_path(relative: str) -> str:
    """Resolve a path that works for dev and PyInstaller builds."""
    import sys
    try:
        base = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, relative)


# ---------------------------------------------------------------------------
# Per-NPC art prefix.  Extend this dict when new art arrives.
# ---------------------------------------------------------------------------

NPC_ART_PREFIX: dict[str, str] = {
    # npc_id  → filename prefix inside assets/
    "old_weary":    "gob",       # placeholder — swap to "weary" later
    "messy_goblin": "gob",
}
_DEFAULT_ART_PREFIX = "gob"


class UIPanel:
    """All-in-one HUD drawn on top of the game view every frame."""

    # Layout constants
    MINIMAP_SIZE = 160          # pixels (square)
    MINIMAP_MARGIN = 10
    BAR_WIDTH = 200
    BAR_HEIGHT = 18
    BAR_SEGMENTS = 10
    BAR_MARGIN = 10
    PORTRAIT_SIZE = 128         # target display size (square)
    PORTRAIT_MARGIN = 10
    NPC_RANGE = 4               # Manhattan-tile proximity

    def __init__(self, screen_width: int, screen_height: int):
        self.sw = screen_width
        self.sh = screen_height

        # Load face PNGs
        self._portraits: dict[str, pygame.Surface] = {}
        self._load_portraits()

    # ------------------------------------------------------------------
    # Portrait loading
    # ------------------------------------------------------------------

    def _load_portraits(self):
        """Load all ``<prefix>_*.png`` portraits + ``unknown.png``."""
        assets = Path(_resource_path("assets"))
        # Collect every unique prefix
        prefixes = set(NPC_ART_PREFIX.values())
        prefixes.add(_DEFAULT_ART_PREFIX)

        for prefix in prefixes:
            for suffix in ("neg3", "neg2", "neg1", "neutral",
                           "pos1", "pos2", "pos3", "puzzled"):
                fn = f"{prefix}_{suffix}.png"
                fp = assets / fn
                if fp.exists():
                    try:
                        img = pygame.image.load(str(fp)).convert_alpha()
                        self._portraits[fn] = img
                    except Exception as e:
                        print(f"[UIPanel] Error loading {fn}: {e}")

        # fallback unknown portrait
        unknown = assets / "unknown.png"
        if unknown.exists():
            try:
                self._portraits["unknown.png"] = pygame.image.load(str(unknown)).convert_alpha()
            except Exception as e:
                print(f"[UIPanel] Error loading unknown.png: {e}")

    def _get_portrait(self, npc_id: str, npc_state: NPCState) -> pygame.Surface | None:
        """Select the correct portrait for an NPC given its current state."""
        prefix = NPC_ART_PREFIX.get(npc_id, _DEFAULT_ART_PREFIX)

        if npc_state.is_puzzled:
            key = f"{prefix}_puzzled.png"
        else:
            es = npc_state.emotional_state
            if es == 0:
                key = f"{prefix}_neutral.png"
            elif es > 0:
                key = f"{prefix}_pos{es}.png"
            else:
                key = f"{prefix}_neg{abs(es)}.png"

        return self._portraits.get(key) or self._portraits.get("unknown.png")

    # ------------------------------------------------------------------
    # NPC proximity
    # ------------------------------------------------------------------

    @staticmethod
    def nearest_npc_in_range(
        player_row: float,
        player_col: float,
        maze: Maze,
        npc_states: dict[str, NPCState],
        radius: int = 4,
    ) -> Optional[tuple[str, Position]]:
        """Return (npc_id, pos) of the closest NPC within *radius* Manhattan
        tiles of the player, or ``None``."""
        best: Optional[tuple[str, Position, float]] = None
        for cell in maze.all_cells():
            nid = cell.npc_id
            if nid is None:
                continue
            dist = abs(cell.pos.row - player_row) + abs(cell.pos.col - player_col)
            if dist <= radius:
                if best is None or dist < best[2]:
                    best = (nid, cell.pos, dist)
        if best is not None:
            return best[0], best[1]
        return None

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_segmented_bar(
        self,
        surface: pygame.Surface,
        x: int, y: int,
        current: int, maximum: int,
        fill_color: tuple[int, int, int],
        label: str,
    ):
        """Draw a bar with *BAR_SEGMENTS* notches."""
        font = pygame.font.Font(None, 20)
        seg_w = self.BAR_WIDTH // self.BAR_SEGMENTS
        total_w = seg_w * self.BAR_SEGMENTS

        # Background
        pygame.draw.rect(surface, (30, 30, 30), (x, y, total_w, self.BAR_HEIGHT))

        # Filled segments
        filled = int(self.BAR_SEGMENTS * (current / maximum)) if maximum > 0 else 0
        for i in range(filled):
            sx = x + i * seg_w + 1
            pygame.draw.rect(surface, fill_color,
                             (sx, y + 1, seg_w - 2, self.BAR_HEIGHT - 2))

        # Segment dividers
        for i in range(1, self.BAR_SEGMENTS):
            dx = x + i * seg_w
            pygame.draw.line(surface, (60, 60, 60), (dx, y), (dx, y + self.BAR_HEIGHT))

        # Border
        pygame.draw.rect(surface, (180, 180, 180), (x, y, total_w, self.BAR_HEIGHT), 1)

        # Label
        txt = font.render(f"{label}: {current}/{maximum}", True, (220, 220, 220))
        surface.blit(txt, (x + 4, y + 1))

    # ------------------------------------------------------------------
    # Minimap
    # ------------------------------------------------------------------

    def _draw_minimap(
        self,
        surface: pygame.Surface,
        game_state,
        player_row: float,
        player_col: float,
    ):
        """Simple grid minimap — visited tiles bright, rest dark/hidden."""
        mm_x = self.MINIMAP_MARGIN
        mm_y = self.MINIMAP_MARGIN
        mm_size = self.MINIMAP_SIZE

        # Semi-transparent panel
        panel = pygame.Surface((mm_size, mm_size), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 180))

        h, w = game_state.height, game_state.width
        if h == 0 or w == 0:
            surface.blit(panel, (mm_x, mm_y))
            return

        cell_w = (mm_size - 4) / w
        cell_h = (mm_size - 4) / h
        cell_sz = min(cell_w, cell_h)
        # Centre the grid inside the panel
        ox = (mm_size - cell_sz * w) / 2
        oy = (mm_size - cell_sz * h) / 2

        for pos in game_state.fog:
            r, c = pos.row, pos.col
            fogged = game_state.is_fogged(pos)
            visited = pos in game_state.visited

            if fogged and not visited:
                continue  # completely unknown

            rx = int(ox + c * cell_sz)
            ry = int(oy + r * cell_sz)
            rw = max(1, int(cell_sz - 1))
            rh = max(1, int(cell_sz - 1))

            if visited:
                color = (120, 120, 140)  # explored
            else:
                color = (50, 50, 60)     # revealed-by-fog but not stepped on

            pygame.draw.rect(panel, color, (rx, ry, rw, rh))

        # Player dot
        px = int(ox + player_col * cell_sz)
        py = int(oy + player_row * cell_sz)
        dot_r = max(2, int(cell_sz * 0.6))
        pygame.draw.circle(panel, (0, 255, 100), (px, py), dot_r)

        # NPC dots (only if tile is revealed)
        for cell in game_state.maze.all_cells():
            if cell.npc_id and not game_state.is_fogged(cell.pos):
                nx = int(ox + cell.pos.col * cell_sz)
                ny = int(oy + cell.pos.row * cell_sz)
                npc_s = game_state.npc_states.get(cell.npc_id)
                if npc_s and npc_s.resolved:
                    dot_col = (100, 255, 100)
                else:
                    dot_col = (100, 180, 255)
                pygame.draw.circle(panel, dot_col, (nx, ny), max(2, int(cell_sz * 0.4)))

        # Mobile NPC dots (only if their tile is revealed)
        if hasattr(game_state, 'mobile_npcs'):
            from maze import Position
            for npc in game_state.mobile_npcs:
                if npc.resolved:
                    continue
                npc_tile = Position(int(npc.float_row), int(npc.float_col))
                if game_state.is_fogged(npc_tile):
                    continue
                mx = int(ox + npc.float_col * cell_sz)
                my = int(oy + npc.float_row * cell_sz)
                pygame.draw.circle(panel, npc.color, (mx, my), max(2, int(cell_sz * 0.5)))

        surface.blit(panel, (mm_x, mm_y))

        # Border
        pygame.draw.rect(surface, (160, 160, 160),
                         (mm_x, mm_y, mm_size, mm_size), 1)

    # ------------------------------------------------------------------
    # NPC portrait box
    # ------------------------------------------------------------------

    def _draw_npc_portrait(
        self,
        surface: pygame.Surface,
        npc_id: Optional[str],
        npc_state: Optional[NPCState],
        npc_name: str,
    ):
        """Draw portrait box in the bottom-right corner."""
        size = self.PORTRAIT_SIZE
        margin = self.PORTRAIT_MARGIN
        bx = self.sw - size - margin
        by = self.sh - size - margin - 24  # leave room for name text

        # Panel background
        panel = pygame.Surface((size, size), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 180))

        if npc_id and npc_state:
            portrait = self._get_portrait(npc_id, npc_state)
        else:
            portrait = self._portraits.get("unknown.png")

        if portrait:
            scaled = pygame.transform.smoothscale(portrait, (size, size))
            panel.blit(scaled, (0, 0))

        surface.blit(panel, (bx, by))
        pygame.draw.rect(surface, (160, 160, 160), (bx, by, size, size), 1)

        # Name label
        font = pygame.font.Font(None, 22)
        label = npc_name if npc_name else "???"
        txt = font.render(label, True, (220, 220, 220))
        tr = txt.get_rect(centerx=bx + size // 2, top=by + size + 2)
        surface.blit(txt, tr)

    # ------------------------------------------------------------------
    # Master draw call
    # ------------------------------------------------------------------

    def draw(
        self,
        surface: pygame.Surface,
        game_state,
        player_row: float,
        player_col: float,
        maze: Maze,
        npc_registry: dict[str, dict],
    ):
        """Render the full HUD overlay."""
        # -- Minimap (top-left) --
        self._draw_minimap(surface, game_state, player_row, player_col)

        # -- Bars (top-right) --
        bar_x = self.sw - self.BAR_WIDTH - self.BAR_MARGIN
        bar_y = self.BAR_MARGIN
        self._draw_segmented_bar(
            surface, bar_x, bar_y,
            game_state.hp, game_state.max_hp,
            (200, 40, 40), "HP",
        )
        bar_y += self.BAR_HEIGHT + 6
        self._draw_segmented_bar(
            surface, bar_x, bar_y,
            game_state.will, game_state.max_will,
            (50, 100, 220), "Will",
        )

        # -- NPC Portrait (bottom-right) --
        nearby = self.nearest_npc_in_range(
            player_row, player_col, maze,
            game_state.npc_states, radius=self.NPC_RANGE,
        )
        if nearby:
            npc_id, _pos = nearby
            npc_state = game_state.npc_states.get(npc_id)
            name = npc_registry.get(npc_id, {}).get("name", npc_id)
        else:
            npc_id = None
            npc_state = None
            name = ""

        self._draw_npc_portrait(surface, npc_id, npc_state, name)
