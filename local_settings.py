# local_settings.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class LocalSettings:
    # Rendering / timing
    target_fps: int = 60
    animation_fps: int = 12

    # Movement
    character_speed_tiles_per_second: float = 4.0

    # Debug
    debug_overlay_enabled: bool = False
    debug_scale: float = 1.0

    # Dungeon generation defaults (tweak later if your project wants different)
    dungeon_width: int = 40
    dungeon_height: int = 25
    dungeon_max_rooms: int = 12
    dungeon_min_room_size: int = 4
    dungeon_max_room_size: int = 9


def load_local_settings() -> LocalSettings:
    # Return an object with attributes used throughout the codebase
    return LocalSettings()
