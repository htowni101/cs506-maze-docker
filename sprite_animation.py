"""
sprite_animation.py — Sprite-Sheet Animator for Isometric Characters

Loads a sprite sheet laid out as 8 columns × 15 rows of 128×256 frames.
Each column is one of eight compass directions the character can face.

Column layout (0-indexed):
    0=SE  1=E  2=NE  3=N  4=NW  5=W  6=SW  7=S
"""
import pygame
from pathlib import Path


class SpriteAnimator:
    """Extracts and plays back walk-cycle frames from a sprite sheet."""

    # Column index for each compass direction
    DIRECTION_COLUMNS: dict[str, int] = {
        "SE": 0, "E": 1, "NE": 2, "N": 3,
        "NW": 4, "W": 5, "SW": 6, "S": 7,
    }

    FRAME_WIDTH = 128
    FRAME_HEIGHT = 256
    FRAME_COUNT = 15  # rows per direction

    def __init__(self, sprite_sheet_path: str, fps: int = 10):
        """
        Parameters
        ----------
        sprite_sheet_path : str
            Absolute or relative path to the sprite-sheet PNG.
        fps : int
            Playback speed in frames-per-second (default 10).
        """
        image = pygame.image.load(sprite_sheet_path)

        if pygame.display.get_surface() is not None:
            self.sheet = image.convert_alpha()
        else:
            self.sheet = image
        self.fps = fps

        # direction (upper) -> list[Surface]
        self.frames: dict[str, list[pygame.Surface]] = {}
        self._extract_frames()

        # Animation state
        self.current_direction: str = "SW"
        self.current_frame: int = 0
        self.animation_timer: float = 0.0
        self.is_moving: bool = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_frames(self):
        """Cut every 128×256 cell out of the sheet."""
        for direction, col in self.DIRECTION_COLUMNS.items():
            frames: list[pygame.Surface] = []
            for row in range(self.FRAME_COUNT):
                x = col * self.FRAME_WIDTH
                y = row * self.FRAME_HEIGHT
                rect = pygame.Rect(x, y, self.FRAME_WIDTH, self.FRAME_HEIGHT)
                frame = self.sheet.subsurface(rect).copy()
                frames.append(frame)
            self.frames[direction] = frames

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_direction(self, direction: str):
        """Change facing direction (case-insensitive, e.g. 'NE' or 'ne')."""
        direction = direction.upper()
        if direction not in self.DIRECTION_COLUMNS:
            return
        if self.current_direction != direction:
            self.current_direction = direction
            self.current_frame = 0
            self.animation_timer = 0.0

    def update(self, dt_ms: float):
        """Advance the animation by *dt_ms* milliseconds."""
        if self.is_moving:
            self.animation_timer += dt_ms
            frame_duration = 1000.0 / self.fps
            while self.animation_timer >= frame_duration:
                self.animation_timer -= frame_duration
                self.current_frame = (self.current_frame + 1) % self.FRAME_COUNT
        else:
            # Idle — hold frame 0 (standing pose)
            self.current_frame = 0
            self.animation_timer = 0.0

    def get_frame(self) -> pygame.Surface:
        """Return the current animation frame surface."""
        return self.frames[self.current_direction][self.current_frame]

    def get_scaled_frame(self, scale: float) -> pygame.Surface:
        """Return the current frame scaled by *scale*."""
        frame = self.get_frame()
        if scale == 1.0:
            return frame
        w = max(1, int(frame.get_width() * scale))
        h = max(1, int(frame.get_height() * scale))
        return pygame.transform.smoothscale(frame, (w, h))

    def reset(self):
        """Reset animation to idle facing SW."""
        self.current_direction = "SW"
        self.current_frame = 0
        self.animation_timer = 0.0
        self.is_moving = False
