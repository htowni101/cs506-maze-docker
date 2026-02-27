"""
db.py — Persistence Layer (JSON I/O)

Stores and retrieves game state as JSON-safe primitives.

CONSTRAINTS:
  - Cannot import maze or main.
  - All stored values must be JSON-serialisable primitives
    (str, int, float, bool, None, list, dict).
  - Complex objects (Enums, Position dataclasses) must be converted
    to/from plain dicts/strings BEFORE reaching this layer.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp string (with microseconds for uniqueness)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    return str(uuid.uuid4())


# Type alias for "any JSON-safe value"
AnyJSON = Any  # str | int | float | bool | None | list | dict


# ---------------------------------------------------------------------------
# Record DTOs — plain dataclasses returned to main.py
# ---------------------------------------------------------------------------

@dataclass
class PlayerRecord:
    id: str
    handle: str
    created_at: str


@dataclass
class GameRecord:
    id: str
    player_id: str
    maze_id: str
    maze_version: str
    state: dict[str, AnyJSON]       # opaque to db — engine owns the schema
    status: str                      # "in_progress" | "completed"
    created_at: str
    updated_at: str


@dataclass
class ScoreRecord:
    id: str
    player_id: str
    game_id: str
    maze_id: str
    maze_version: str
    metrics: dict[str, AnyJSON]
    created_at: str


# ---------------------------------------------------------------------------
# Repository Interface (duck-typed protocol)
# ---------------------------------------------------------------------------

class GameRepository:
    """
    Abstract base for persistence backends.

    main.py depends on this interface only.  Concrete implementations
    live below (JsonGameRepository today; SqliteGameRepository later).
    """

    # -- Player ops --
    def get_player(self, player_id: str) -> Optional[PlayerRecord]:
        raise NotImplementedError

    def get_or_create_player(self, handle: str) -> PlayerRecord:
        raise NotImplementedError

    # -- Game ops --
    def create_game(
        self,
        player_id: str,
        maze_id: str,
        maze_version: str,
        initial_state: dict,
    ) -> GameRecord:
        raise NotImplementedError

    def get_game(self, game_id: str) -> Optional[GameRecord]:
        raise NotImplementedError

    def save_game(
        self,
        game_id: str,
        state: dict,
        status: str = "in_progress",
    ) -> GameRecord:
        raise NotImplementedError

    # -- Score ops --
    def record_score(
        self,
        player_id: str,
        game_id: str,
        maze_id: str,
        maze_version: str,
        metrics: dict,
    ) -> ScoreRecord:
        raise NotImplementedError

    def top_scores(
        self,
        maze_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[ScoreRecord]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# JSON-file implementation
# ---------------------------------------------------------------------------

class JsonGameRepository(GameRepository):
    """
    Stores all data in a single JSON file.

    File shape:
        {
            "schema_version": 1,
            "players": { "<id>": { ... } },
            "games":   { "<id>": { ... } },
            "scores":  { "<id>": { ... } }
        }
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, Any] = self._load()

    # -- internal I/O --

    def _empty_store(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "players": {},
            "games": {},
            "scores": {},
        }

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("schema_version") != self.SCHEMA_VERSION:
                # Future: migration logic goes here
                pass
            return data
        return self._empty_store()
        
    def _flush(self) -> None:
        """Write-then-rename for crash safety."""
        import os
        import time
        import tempfile
        from pathlib import Path

        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create a temporary file in the same directory to allow atomic replacement
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)

        try:
            # Write the full JSON payload, then flush and fsync to ensure durability
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Replace the target file; retry briefly if the filesystem reporst as temporarily unavailable
            delays = [0.05, 0.10, 0.15, 0.25, 0.35, 0.50, 0.75]  # ~2.15s total
            for d in delays:
                try:
                    os.replace(str(tmp_path), str(path))
                    return
                except PermissionError:
                    time.sleep(d)

            # Final attempt (raise if still locked) 
            os.replace(str(tmp_path), str(path))

        finally:
            # Cleanup: remove the temporary file if it exists
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    
    # -- Player ops --

    def get_player(self, player_id: str) -> Optional[PlayerRecord]:
        raw = self._data["players"].get(player_id)
        if raw is None:
            return None
        return PlayerRecord(**raw)

    def get_or_create_player(self, handle: str) -> PlayerRecord:
        # Search by handle first
        for raw in self._data["players"].values():
            if raw["handle"] == handle:
                return PlayerRecord(**raw)
        # Create new
        rec = PlayerRecord(id=_new_id(), handle=handle, created_at=_utc_now_iso())
        self._data["players"][rec.id] = asdict(rec)
        self._flush()
        return rec

    # -- Game ops --

    def create_game(
        self,
        player_id: str,
        maze_id: str,
        maze_version: str,
        initial_state: dict,
    ) -> GameRecord:
        now = _utc_now_iso()
        rec = GameRecord(
            id=_new_id(),
            player_id=player_id,
            maze_id=maze_id,
            maze_version=maze_version,
            state=initial_state,
            status="in_progress",
            created_at=now,
            updated_at=now,
        )
        self._data["games"][rec.id] = asdict(rec)
        self._flush()
        return rec

    def get_game(self, game_id: str) -> Optional[GameRecord]:
        raw = self._data["games"].get(game_id)
        if raw is None:
            return None
        return GameRecord(**raw)

    def save_game(
        self,
        game_id: str,
        state: dict,
        status: str = "in_progress",
    ) -> GameRecord:
        raw = self._data["games"].get(game_id)
        if raw is None:
            raise KeyError(f"No game with id={game_id!r}")
        raw["state"] = state
        raw["status"] = status
        raw["updated_at"] = _utc_now_iso()
        self._data["games"][game_id] = raw
        self._flush()
        return GameRecord(**raw)

    # -- Score ops --

    def record_score(
        self,
        player_id: str,
        game_id: str,
        maze_id: str,
        maze_version: str,
        metrics: dict,
    ) -> ScoreRecord:
        rec = ScoreRecord(
            id=_new_id(),
            player_id=player_id,
            game_id=game_id,
            maze_id=maze_id,
            maze_version=maze_version,
            metrics=metrics,
            created_at=_utc_now_iso(),
        )
        self._data["scores"][rec.id] = asdict(rec)
        self._flush()
        return rec

    def top_scores(
        self,
        maze_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[ScoreRecord]:
        scores = list(self._data["scores"].values())
        if maze_id:
            scores = [s for s in scores if s["maze_id"] == maze_id]
        # Sort by move_count ascending (fewer moves = better)
        scores.sort(key=lambda s: s["metrics"].get("move_count", 9999))
        return [ScoreRecord(**s) for s in scores[:limit]]


# ---------------------------------------------------------------------------
# Factory — future-proofs for SQLite backend
# ---------------------------------------------------------------------------

def open_repo(path: str | Path) -> GameRepository:
    """
    Open a repository at *path*.

    If the path suffix is ``.db``, return a SqliteGameRepository (not yet
    implemented).  Otherwise, return a JsonGameRepository.
    """
    path = Path(path)
    if path.suffix == ".db":
        raise NotImplementedError("SQLite backend not yet implemented")
    return JsonGameRepository(path)
