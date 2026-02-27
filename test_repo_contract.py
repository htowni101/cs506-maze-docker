"""
test_repo_contract.py — DB Persistence Contract Tests

Tests ONLY db.py.  Uses a temporary file for each test for isolation.
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
    JsonGameRepository,
    open_repo,
)


class _RepoTestBase(unittest.TestCase):
    """Helper: creates a fresh temp JSON file per test."""

    def setUp(self):
        self._tmpfile = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        )
        self._tmpfile.close()
        self.path = self._tmpfile.name
        # Make sure the file doesn't exist so repo starts clean
        os.unlink(self.path)
        self.repo = JsonGameRepository(self.path)

    def tearDown(self):
        for f in [self.path, self.path.replace(".json", ".tmp")]:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass


# ===================================================================
# 1) Player operations
# ===================================================================

class TestPlayerOps(_RepoTestBase):
    """D-P01 … D-P04"""

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


# ===================================================================
# 2) Game operations
# ===================================================================

class TestGameOps(_RepoTestBase):
    """D-G01 … D-G07"""

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


# ===================================================================
# 3) Score operations
# ===================================================================

class TestScoreOps(_RepoTestBase):
    """D-S01 … D-S05"""

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


# ===================================================================
# 4) Persistence (I/O)
# ===================================================================

class TestPersistence(_RepoTestBase):
    """D-IO01 … D-IO03"""

    def test_data_survives_reload(self):  # D-IO01
        p = self.repo.get_or_create_player("Persist")
        g = self.repo.create_game(p.id, "m", "1", {"key": "val"})
        # Create a brand-new repo from the same file
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
            data = json.load(f)  # will raise if invalid
        self.assertIsInstance(data, dict)


# ===================================================================
# 5) Constraint enforcement
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
