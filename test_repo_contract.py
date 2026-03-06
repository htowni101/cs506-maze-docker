"""
test_repo_contract.py -- DB Persistence Contract Tests

Tests db.py with both JSON and SQLite backends.
Uses a temporary file for each test for isolation.
"""
import json
import os
import tempfile
import time
import unittest
import ast
from pathlib import Path

from db import (
    PlayerRecord,
    GameRecord,
    ScoreRecord,
    NPCRecord,
    DungeonLayoutRecord,
    JsonGameRepository,
    SqliteGameRepository,
    open_repo,
)


# ---------------------------------------------------------------------------
# Helpers -- parameterised base classes for both backends
# ---------------------------------------------------------------------------


class _JsonRepoBase(unittest.TestCase):
    """Creates a fresh temp JSON file per test."""

    def setUp(self):
        self._tmpfile = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        )
        self._tmpfile.close()
        self.path = self._tmpfile.name
        os.unlink(self.path)
        self.repo = JsonGameRepository(self.path)

    def tearDown(self):
        for f in [self.path, self.path.replace(".json", ".tmp")]:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass


class _SqliteRepoBase(unittest.TestCase):
    """Creates a fresh temp SQLite file per test."""

    def setUp(self):
        self._tmpfile = tempfile.NamedTemporaryFile(
            suffix=".db", delete=False
        )
        self._tmpfile.close()
        self.path = self._tmpfile.name
        os.unlink(self.path)
        self.repo = SqliteGameRepository(self.path)

    def tearDown(self):
        self.repo.dispose()
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass# ===================================================================
# Player ops  (D-P series)
# ===================================================================

class _PlayerOpsMixin:

    def test_create_player(self):  # D-P01
        p = self.repo.get_or_create_player("Hero")
        self.assertIsInstance(p, PlayerRecord)
        self.assertEqual(p.handle, "Hero")
        self.assertTrue(len(p.id) > 0)

    def test_idempotent_create(self):  # D-P02
        p1 = self.repo.get_or_create_player("Hero")
        p2 = self.repo.get_or_create_player("Hero")
        self.assertEqual(p1.id, p2.id)

    def test_get_by_id(self):  # D-P03
        p = self.repo.get_or_create_player("Hero")
        fetched = self.repo.get_player(p.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, p.id)
        self.assertEqual(fetched.handle, "Hero")

    def test_get_missing_player(self):  # D-P04
        self.assertIsNone(self.repo.get_player("nonexistent-id"))


class TestPlayerOpsJson(_PlayerOpsMixin, _JsonRepoBase):
    """D-P (JSON backend)"""

class TestPlayerOpsSqlite(_PlayerOpsMixin, _SqliteRepoBase):
    """D-P (SQLite backend)"""


# ===================================================================
# Game ops  (D-G series)
# ===================================================================

class _GameOpsMixin:

    def _make_player(self):
        return self.repo.get_or_create_player("Tester")

    def test_create_game(self):  # D-G01
        p = self._make_player()
        g = self.repo.create_game(
            player_id=p.id,
            maze_id="maze-3x3-v1",
            maze_version="1.0",
            initial_state={"pos": {"row": 0, "col": 0}},
        )
        self.assertIsInstance(g, GameRecord)
        self.assertEqual(g.status, "in_progress")
        self.assertEqual(g.maze_id, "maze-3x3-v1")

    def test_get_game(self):  # D-G02
        p = self._make_player()
        g = self.repo.create_game(p.id, "m", "1", {"x": 1})
        fetched = self.repo.get_game(g.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, g.id)

    def test_save_game_updates_state(self):  # D-G03
        p = self._make_player()
        g = self.repo.create_game(p.id, "m", "1", {"turn": 0})
        self.repo.save_game(g.id, {"turn": 5})
        fetched = self.repo.get_game(g.id)
        self.assertEqual(fetched.state["turn"], 5)

    def test_save_game_updates_status(self):  # D-G04
        p = self._make_player()
        g = self.repo.create_game(p.id, "m", "1", {})
        self.repo.save_game(g.id, {}, "completed")
        fetched = self.repo.get_game(g.id)
        self.assertEqual(fetched.status, "completed")

    def test_save_game_updates_timestamp(self):  # D-G05
        p = self._make_player()
        g = self.repo.create_game(p.id, "m", "1", {})
        old_ts = g.updated_at
        time.sleep(0.05)
        self.repo.save_game(g.id, {"new": True})
        fetched = self.repo.get_game(g.id)
        self.assertNotEqual(fetched.updated_at, old_ts)

    def test_get_missing_game(self):  # D-G06
        self.assertIsNone(self.repo.get_game("no-such-game"))

    def test_state_is_opaque_dict(self):  # D-G07
        p = self._make_player()
        complex_state = {
            "pos": {"row": 1, "col": 2},
            "custom_key": [1, 2, 3],
            "nested": {"a": {"b": True}},
        }
        g = self.repo.create_game(p.id, "m", "1", complex_state)
        fetched = self.repo.get_game(g.id)
        self.assertEqual(fetched.state, complex_state)


class TestGameOpsJson(_GameOpsMixin, _JsonRepoBase):
    """D-G (JSON backend)"""

class TestGameOpsSqlite(_GameOpsMixin, _SqliteRepoBase):
    """D-G (SQLite backend)"""


# ===================================================================
# Score ops  (D-S series)
# ===================================================================

class _ScoreOpsMixin:

    def _setup_game(self):
        p = self.repo.get_or_create_player("Scorer")
        g = self.repo.create_game(p.id, "maze-3x3-v1", "1.0", {})
        return p, g

    def test_record_score(self):  # D-S01
        p, g = self._setup_game()
        s = self.repo.record_score(p.id, g.id, "maze-3x3-v1", "1.0", {"move_count": 10})
        self.assertIsInstance(s, ScoreRecord)
        self.assertEqual(s.maze_id, "maze-3x3-v1")
        self.assertEqual(s.metrics["move_count"], 10)

    def test_top_scores_returns_list(self):  # D-S02
        p, g = self._setup_game()
        self.repo.record_score(p.id, g.id, "m", "1", {"move_count": 5})
        result = self.repo.top_scores()
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(s, ScoreRecord) for s in result))

    def test_top_scores_ordered(self):  # D-S03
        p, g = self._setup_game()
        self.repo.record_score(p.id, g.id, "m", "1", {"move_count": 20})
        self.repo.record_score(p.id, g.id, "m", "1", {"move_count": 5})
        self.repo.record_score(p.id, g.id, "m", "1", {"move_count": 12})
        result = self.repo.top_scores()
        counts = [s.metrics["move_count"] for s in result]
        self.assertEqual(counts, sorted(counts))

    def test_top_scores_filter_maze(self):  # D-S04
        p, g = self._setup_game()
        self.repo.record_score(p.id, g.id, "maze-A", "1", {"move_count": 5})
        self.repo.record_score(p.id, g.id, "maze-B", "1", {"move_count": 3})
        result = self.repo.top_scores(maze_id="maze-A")
        self.assertTrue(all(s.maze_id == "maze-A" for s in result))

    def test_top_scores_limit(self):  # D-S05
        p, g = self._setup_game()
        for i in range(10):
            self.repo.record_score(p.id, g.id, "m", "1", {"move_count": i})
        result = self.repo.top_scores(limit=2)
        self.assertLessEqual(len(result), 2)


class TestScoreOpsJson(_ScoreOpsMixin, _JsonRepoBase):
    """D-S (JSON backend)"""

class TestScoreOpsSqlite(_ScoreOpsMixin, _SqliteRepoBase):
    """D-S (SQLite backend)"""


# ===================================================================
# NPC state ops  (D-N series)
# ===================================================================

class _NPCStateMixin:

    def _setup_game(self):
        p = self.repo.get_or_create_player("NPCTest")
        g = self.repo.create_game(p.id, "m", "1", {})
        return p, g

    def test_save_and_get_npc_state(self):  # D-N01
        _, g = self._setup_game()
        rec = self.repo.save_npc_state(g.id, "old_weary", {
            "emotional_state": -2,
            "resolved": False,
            "resolution": "",
            "last_emotion_category": "anger",
            "interaction_count": 2,
        })
        self.assertIsInstance(rec, NPCRecord)
        self.assertEqual(rec.npc_id, "old_weary")
        self.assertEqual(rec.emotional_state, -2)

    def test_get_npc_states_returns_list(self):  # D-N02
        _, g = self._setup_game()
        self.repo.save_npc_state(g.id, "old_weary", {
            "emotional_state": -1, "resolved": False,
            "resolution": "", "last_emotion_category": "fear",
            "interaction_count": 1,
        })
        self.repo.save_npc_state(g.id, "messy_goblin", {
            "emotional_state": 2, "resolved": False,
            "resolution": "", "last_emotion_category": "happy",
            "interaction_count": 2,
        })
        states = self.repo.get_npc_states(g.id)
        self.assertIsInstance(states, list)
        ids = {s.npc_id for s in states}
        self.assertIn("old_weary", ids)
        self.assertIn("messy_goblin", ids)

    def test_no_npc_states_returns_empty(self):  # D-N03
        _, g = self._setup_game()
        self.assertEqual(self.repo.get_npc_states(g.id), [])

    def test_upsert_overwrites(self):  # D-N04
        _, g = self._setup_game()
        self.repo.save_npc_state(g.id, "old_weary", {
            "emotional_state": -1, "resolved": False,
            "resolution": "", "last_emotion_category": "anger",
            "interaction_count": 1,
        })
        self.repo.save_npc_state(g.id, "old_weary", {
            "emotional_state": -3, "resolved": True,
            "resolution": "cruel_success",
            "last_emotion_category": "anger",
            "interaction_count": 3,
        })
        states = self.repo.get_npc_states(g.id)
        ow = [s for s in states if s.npc_id == "old_weary"]
        self.assertEqual(len(ow), 1)
        self.assertEqual(ow[0].emotional_state, -3)
        self.assertTrue(ow[0].resolved)


class TestNPCStateJson(_NPCStateMixin, _JsonRepoBase):
    """D-N (JSON backend)"""

class TestNPCStateSqlite(_NPCStateMixin, _SqliteRepoBase):
    """D-N (SQLite backend)"""


# ===================================================================
# Dungeon layout ops  (D-L series)
# ===================================================================

class _DungeonLayoutMixin:

    def _setup_game(self):
        p = self.repo.get_or_create_player("LayoutTest")
        g = self.repo.create_game(p.id, "m", "1", {})
        return p, g

    def test_save_and_get_layout(self):  # D-L01
        _, g = self._setup_game()
        rec = self.repo.save_dungeon_layout(
            game_id=g.id, seed=42, width=60, height=40, max_rooms=12,
            tile_data={"rooms": [{"x": 1, "y": 2}]},
        )
        self.assertIsInstance(rec, DungeonLayoutRecord)
        self.assertEqual(rec.seed, 42)
        self.assertEqual(rec.width, 60)
        self.assertEqual(rec.tile_data["rooms"][0]["x"], 1)

    def test_get_missing_layout(self):  # D-L02
        _, g = self._setup_game()
        self.assertIsNone(self.repo.get_dungeon_layout(g.id))

    def test_layout_upsert_overwrites(self):  # D-L03
        _, g = self._setup_game()
        self.repo.save_dungeon_layout(g.id, seed=1, width=10, height=10, max_rooms=3)
        self.repo.save_dungeon_layout(g.id, seed=2, width=20, height=20, max_rooms=6)
        rec = self.repo.get_dungeon_layout(g.id)
        self.assertEqual(rec.seed, 2)
        self.assertEqual(rec.width, 20)


class TestDungeonLayoutJson(_DungeonLayoutMixin, _JsonRepoBase):
    """D-L (JSON backend)"""

class TestDungeonLayoutSqlite(_DungeonLayoutMixin, _SqliteRepoBase):
    """D-L (SQLite backend)"""


# ===================================================================
# Persistence (JSON-specific I/O tests)
# ===================================================================

class TestJSONPersistence(_JsonRepoBase):
    """D-IO01 -- D-IO03"""

    def test_data_survives_reload(self):  # D-IO01
        p = self.repo.get_or_create_player("Persist")
        g = self.repo.create_game(p.id, "m", "1", {"key": "val"})
        repo2 = JsonGameRepository(self.path)
        fetched = repo2.get_game(g.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.state["key"], "val")

    def test_schema_version_present(self):  # D-IO02
        self.repo.get_or_create_player("anyone")
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema_version"], 1)

    def test_json_is_valid(self):  # D-IO03
        self.repo.get_or_create_player("anyone")
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)


# ===================================================================
# open_repo() factory
# ===================================================================

class TestOpenRepoFactory(unittest.TestCase):
    """D-F01 -- D-F02"""

    def test_json_extension(self):  # D-F01
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        os.unlink(path)
        try:
            repo = open_repo(path)
            self.assertIsInstance(repo, JsonGameRepository)
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_db_extension(self):  # D-F02
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        os.unlink(path)
        try:
            repo = open_repo(path)
            self.assertIsInstance(repo, SqliteGameRepository)
            repo.dispose()
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


# ===================================================================
# Constraint enforcement
# ===================================================================

class TestDbConstraints(unittest.TestCase):
    """D-C01, D-C02"""

    @classmethod
    def setUpClass(cls):
        src = Path(__file__).parent / "db.py"
        cls.tree = ast.parse(src.read_text(encoding="utf-8"))

    def test_no_import_maze(self):  # D-C01
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "maze")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "maze")

    def test_no_import_main(self):  # D-C02
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "main")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "main")


if __name__ == "__main__":
    unittest.main()
