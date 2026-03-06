"""
db.py — Persistence Layer (JSON + SQLite via SQLModel)

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
# Record DTOs — plain dataclasses returned to callers
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


@dataclass
class NPCRecord:
    id: str
    game_id: str
    npc_id: str
    emotional_state: int
    resolved: bool
    resolution: str
    last_emotion_category: str
    interaction_count: int


@dataclass
class DungeonLayoutRecord:
    id: str
    game_id: str
    seed: int
    width: int
    height: int
    max_rooms: int
    tile_data: dict[str, AnyJSON]


# ---------------------------------------------------------------------------
# Repository Interface (duck-typed protocol)
# ---------------------------------------------------------------------------

class GameRepository:
    """
    Abstract base for persistence backends.

    main.py depends on this interface only.  Concrete implementations
    live below (JsonGameRepository and SqliteGameRepository).
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

    # -- NPC persistence ops (expanded interface) --
    def save_npc_state(
        self,
        game_id: str,
        npc_id: str,
        state_dict: dict,
    ) -> NPCRecord:
        raise NotImplementedError

    def get_npc_states(self, game_id: str) -> list[NPCRecord]:
        raise NotImplementedError

    # -- Dungeon layout persistence (expanded interface) --
    def save_dungeon_layout(
        self,
        game_id: str,
        seed: int,
        width: int,
        height: int,
        max_rooms: int,
        tile_data: dict | None = None,
    ) -> DungeonLayoutRecord:
        raise NotImplementedError

    def get_dungeon_layout(self, game_id: str) -> Optional[DungeonLayoutRecord]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# JSON-file implementation (legacy, kept for backward-compat & tests)
# ---------------------------------------------------------------------------

class JsonGameRepository(GameRepository):
    """
    Stores all data in a single JSON file.

    File shape:
        {
            "schema_version": 1,
            "players": { "<id>": { ... } },
            "games":   { "<id>": { ... } },
            "scores":  { "<id>": { ... } },
            "npc_states": { "<id>": { ... } },
            "dungeon_layouts": { "<id>": { ... } }
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
            "npc_states": {},
            "dungeon_layouts": {},
        }

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("schema_version") != self.SCHEMA_VERSION:
                pass  # future migration
            # Ensure new keys exist for older files
            data.setdefault("npc_states", {})
            data.setdefault("dungeon_layouts", {})
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
        scores.sort(key=lambda s: s["metrics"].get("move_count", 9999))
        return [ScoreRecord(**s) for s in scores[:limit]]

    # -- NPC state ops --

    def save_npc_state(
        self,
        game_id: str,
        npc_id: str,
        state_dict: dict,
    ) -> NPCRecord:
        key = f"{game_id}:{npc_id}"
        rec = NPCRecord(
            id=key,
            game_id=game_id,
            npc_id=npc_id,
            emotional_state=state_dict.get("emotional_state", 0),
            resolved=state_dict.get("resolved", False),
            resolution=state_dict.get("resolution", ""),
            last_emotion_category=state_dict.get("last_emotion_category", ""),
            interaction_count=state_dict.get("interaction_count", 0),
        )
        self._data["npc_states"][key] = asdict(rec)
        self._flush()
        return rec

    def get_npc_states(self, game_id: str) -> list[NPCRecord]:
        results = []
        for raw in self._data["npc_states"].values():
            if raw["game_id"] == game_id:
                results.append(NPCRecord(**raw))
        return results

    # -- Dungeon layout ops --

    def save_dungeon_layout(
        self,
        game_id: str,
        seed: int,
        width: int,
        height: int,
        max_rooms: int,
        tile_data: dict | None = None,
    ) -> DungeonLayoutRecord:
        # Upsert: find existing by game_id
        existing_id = None
        for rid, raw in self._data["dungeon_layouts"].items():
            if raw["game_id"] == game_id:
                existing_id = rid
                break
        rec = DungeonLayoutRecord(
            id=existing_id or _new_id(),
            game_id=game_id,
            seed=seed,
            width=width,
            height=height,
            max_rooms=max_rooms,
            tile_data=tile_data or {},
        )
        self._data["dungeon_layouts"][rec.id] = asdict(rec)
        self._flush()
        return rec

    def get_dungeon_layout(self, game_id: str) -> Optional[DungeonLayoutRecord]:
        for raw in self._data["dungeon_layouts"].values():
            if raw["game_id"] == game_id:
                return DungeonLayoutRecord(**raw)
        return None


# ---------------------------------------------------------------------------
# SQLite implementation via SQLModel
# ---------------------------------------------------------------------------

from sqlmodel import SQLModel, Field, Session, create_engine, select, Column
from sqlalchemy import JSON


class PlayerTable(SQLModel, table=True):
    __tablename__ = "players"
    id: str = Field(primary_key=True)
    handle: str = Field(index=True)
    created_at: str


class GameTable(SQLModel, table=True):
    __tablename__ = "games"
    id: str = Field(primary_key=True)
    player_id: str = Field(index=True)
    maze_id: str
    maze_version: str
    state: dict = Field(sa_column=Column(JSON))
    status: str = Field(default="in_progress")
    created_at: str
    updated_at: str


class ScoreTable(SQLModel, table=True):
    __tablename__ = "scores"
    id: str = Field(primary_key=True)
    player_id: str = Field(index=True)
    game_id: str = Field(index=True)
    maze_id: str
    maze_version: str
    metrics: dict = Field(sa_column=Column(JSON))
    created_at: str


class NPCStateTable(SQLModel, table=True):
    __tablename__ = "npc_states"
    id: str = Field(primary_key=True)
    game_id: str = Field(index=True)
    npc_id: str
    emotional_state: int = Field(default=0)
    resolved: bool = Field(default=False)
    resolution: str = Field(default="")
    last_emotion_category: str = Field(default="")
    interaction_count: int = Field(default=0)


class DungeonLayoutTable(SQLModel, table=True):
    __tablename__ = "dungeon_layouts"
    id: str = Field(primary_key=True)
    game_id: str = Field(index=True, unique=True)
    seed: int
    width: int
    height: int
    max_rooms: int
    tile_data: dict = Field(sa_column=Column(JSON), default={})


class SqliteGameRepository(GameRepository):
    """SQLModel-backed SQLite persistence."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._engine = create_engine(
            f"sqlite:///{self._path}",
            echo=False,
        )
        SQLModel.metadata.create_all(self._engine)

    def _session(self) -> Session:
        return Session(self._engine)

    def dispose(self):
        """Dispose of the engine (release file locks)."""
        self._engine.dispose()

    # -- Player ops --

    def get_player(self, player_id: str) -> Optional[PlayerRecord]:
        with self._session() as s:
            row = s.get(PlayerTable, player_id)
            if row is None:
                return None
            return PlayerRecord(id=row.id, handle=row.handle, created_at=row.created_at)

    def get_or_create_player(self, handle: str) -> PlayerRecord:
        with self._session() as s:
            stmt = select(PlayerTable).where(PlayerTable.handle == handle)
            row = s.exec(stmt).first()
            if row:
                return PlayerRecord(id=row.id, handle=row.handle, created_at=row.created_at)
            new = PlayerTable(id=_new_id(), handle=handle, created_at=_utc_now_iso())
            s.add(new)
            s.commit()
            s.refresh(new)
            return PlayerRecord(id=new.id, handle=new.handle, created_at=new.created_at)

    # -- Game ops --

    def create_game(
        self,
        player_id: str,
        maze_id: str,
        maze_version: str,
        initial_state: dict,
    ) -> GameRecord:
        now = _utc_now_iso()
        row = GameTable(
            id=_new_id(),
            player_id=player_id,
            maze_id=maze_id,
            maze_version=maze_version,
            state=initial_state,
            status="in_progress",
            created_at=now,
            updated_at=now,
        )
        with self._session() as s:
            s.add(row)
            s.commit()
            s.refresh(row)
            return GameRecord(
                id=row.id, player_id=row.player_id,
                maze_id=row.maze_id, maze_version=row.maze_version,
                state=row.state, status=row.status,
                created_at=row.created_at, updated_at=row.updated_at,
            )

    def get_game(self, game_id: str) -> Optional[GameRecord]:
        with self._session() as s:
            row = s.get(GameTable, game_id)
            if row is None:
                return None
            return GameRecord(
                id=row.id, player_id=row.player_id,
                maze_id=row.maze_id, maze_version=row.maze_version,
                state=row.state, status=row.status,
                created_at=row.created_at, updated_at=row.updated_at,
            )

    def save_game(
        self,
        game_id: str,
        state: dict,
        status: str = "in_progress",
    ) -> GameRecord:
        with self._session() as s:
            row = s.get(GameTable, game_id)
            if row is None:
                raise KeyError(f"No game with id={game_id!r}")
            row.state = state
            row.status = status
            row.updated_at = _utc_now_iso()
            s.add(row)
            s.commit()
            s.refresh(row)
            return GameRecord(
                id=row.id, player_id=row.player_id,
                maze_id=row.maze_id, maze_version=row.maze_version,
                state=row.state, status=row.status,
                created_at=row.created_at, updated_at=row.updated_at,
            )

    # -- Score ops --

    def record_score(
        self,
        player_id: str,
        game_id: str,
        maze_id: str,
        maze_version: str,
        metrics: dict,
    ) -> ScoreRecord:
        row = ScoreTable(
            id=_new_id(),
            player_id=player_id,
            game_id=game_id,
            maze_id=maze_id,
            maze_version=maze_version,
            metrics=metrics,
            created_at=_utc_now_iso(),
        )
        with self._session() as s:
            s.add(row)
            s.commit()
            s.refresh(row)
            return ScoreRecord(
                id=row.id, player_id=row.player_id,
                game_id=row.game_id, maze_id=row.maze_id,
                maze_version=row.maze_version, metrics=row.metrics,
                created_at=row.created_at,
            )

    def top_scores(
        self,
        maze_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[ScoreRecord]:
        with self._session() as s:
            stmt = select(ScoreTable)
            if maze_id:
                stmt = stmt.where(ScoreTable.maze_id == maze_id)
            rows = s.exec(stmt).all()
            rows_sorted = sorted(rows, key=lambda r: r.metrics.get("move_count", 9999))
            return [
                ScoreRecord(
                    id=r.id, player_id=r.player_id,
                    game_id=r.game_id, maze_id=r.maze_id,
                    maze_version=r.maze_version, metrics=r.metrics,
                    created_at=r.created_at,
                )
                for r in rows_sorted[:limit]
            ]

    # -- NPC state ops --

    def save_npc_state(
        self,
        game_id: str,
        npc_id: str,
        state_dict: dict,
    ) -> NPCRecord:
        key = f"{game_id}:{npc_id}"
        with self._session() as s:
            row = s.get(NPCStateTable, key)
            if row is None:
                row = NPCStateTable(
                    id=key,
                    game_id=game_id,
                    npc_id=npc_id,
                )
            row.emotional_state = state_dict.get("emotional_state", 0)
            row.resolved = state_dict.get("resolved", False)
            row.resolution = state_dict.get("resolution", "")
            row.last_emotion_category = state_dict.get("last_emotion_category", "")
            row.interaction_count = state_dict.get("interaction_count", 0)
            s.add(row)
            s.commit()
            s.refresh(row)
            return NPCRecord(
                id=row.id, game_id=row.game_id, npc_id=row.npc_id,
                emotional_state=row.emotional_state, resolved=row.resolved,
                resolution=row.resolution,
                last_emotion_category=row.last_emotion_category,
                interaction_count=row.interaction_count,
            )

    def get_npc_states(self, game_id: str) -> list[NPCRecord]:
        with self._session() as s:
            stmt = select(NPCStateTable).where(NPCStateTable.game_id == game_id)
            rows = s.exec(stmt).all()
            return [
                NPCRecord(
                    id=r.id, game_id=r.game_id, npc_id=r.npc_id,
                    emotional_state=r.emotional_state, resolved=r.resolved,
                    resolution=r.resolution,
                    last_emotion_category=r.last_emotion_category,
                    interaction_count=r.interaction_count,
                )
                for r in rows
            ]

    # -- Dungeon layout ops --

    def save_dungeon_layout(
        self,
        game_id: str,
        seed: int,
        width: int,
        height: int,
        max_rooms: int,
        tile_data: dict | None = None,
    ) -> DungeonLayoutRecord:
        with self._session() as s:
            stmt = select(DungeonLayoutTable).where(
                DungeonLayoutTable.game_id == game_id
            )
            row = s.exec(stmt).first()
            if row is None:
                row = DungeonLayoutTable(
                    id=_new_id(),
                    game_id=game_id,
                    seed=seed,
                    width=width,
                    height=height,
                    max_rooms=max_rooms,
                    tile_data=tile_data or {},
                )
            else:
                row.seed = seed
                row.width = width
                row.height = height
                row.max_rooms = max_rooms
                row.tile_data = tile_data or {}
            s.add(row)
            s.commit()
            s.refresh(row)
            return DungeonLayoutRecord(
                id=row.id, game_id=row.game_id,
                seed=row.seed, width=row.width, height=row.height,
                max_rooms=row.max_rooms, tile_data=row.tile_data,
            )

    def get_dungeon_layout(self, game_id: str) -> Optional[DungeonLayoutRecord]:
        with self._session() as s:
            stmt = select(DungeonLayoutTable).where(
                DungeonLayoutTable.game_id == game_id
            )
            row = s.exec(stmt).first()
            if row is None:
                return None
            return DungeonLayoutRecord(
                id=row.id, game_id=row.game_id,
                seed=row.seed, width=row.width, height=row.height,
                max_rooms=row.max_rooms, tile_data=row.tile_data,
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def open_repo(path: str | Path) -> GameRepository:
    """
    Open a repository at *path*.

    .db  → SqliteGameRepository (SQLModel/SQLAlchemy)
    .json → JsonGameRepository (legacy)
    """
    path = Path(path)
    if path.suffix == ".db":
        return SqliteGameRepository(path)
    return JsonGameRepository(path)
