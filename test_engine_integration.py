"""
test_engine_integration.py -- Full Integration Tests

Tests game.py GameState + Game wiring (non-GUI methods) with maze.py
and db.py.  Validates NPC interaction, movement, win/fail conditions.

NOTE: Game.__init__ calls pygame.init(), so we mock pygame.display
to avoid needing an actual display.
"""
import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from maze import (
    Maze,
    Position,
    Direction,
    CellKind,
    build_3x3_maze,
)
from db import JsonGameRepository
from npc_data import NPCState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo():
    """Create a temp JSON repo for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.close()
    path = tmp.name
    os.unlink(path)
    return JsonGameRepository(path), path


def _make_game(maze=None, seed=0):
    """Create a Game instance with pygame display mocked out."""
    if maze is None:
        maze = build_3x3_maze()
    repo, db_path = _make_repo()
    player = repo.get_or_create_player("TestHero")
    game_rec = repo.create_game(player.id, maze.maze_id, maze.maze_version, {"seed": seed})

    # Import game module; mock pygame.display to avoid needing a real screen
    import pygame
    with patch("pygame.display.set_mode") as mock_set_mode, \
         patch("pygame.display.set_caption"), \
         patch("pygame.font.Font", return_value=MagicMock()):
        mock_set_mode.return_value = pygame.Surface((1200, 800))
        from game import Game
        game = Game(
            maze=maze,
            seed=seed,
            repo=repo,
            player_name=player.handle,
        )
    return game, repo, db_path


class _EngineTestBase(unittest.TestCase):

    def setUp(self):
        self.game, self.repo, self._db_path = _make_game()
        self.gs = self.game.game_state
        self.maze = self.game.maze

    def tearDown(self):
        for f in [self._db_path, self._db_path.replace(".json", ".tmp")]:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass

    def _move(self, arrow: str):
        """Move the player (arrow = up/down/left/right)."""
        self.game.try_move(arrow)

    def _move_dir(self, direction: str):
        """Move using compass direction (n/s/e/w)."""
        mapping = {"n": "up", "s": "down", "e": "right", "w": "left"}
        self._move(mapping[direction.lower()])


# ===================================================================
# 1) Initialisation
# ===================================================================

class TestInit(_EngineTestBase):
    """E-I01 ... E-I06"""

    def test_creates_without_error(self):  # E-I01
        self.assertIsNotNone(self.game)

    def test_initial_position_is_start(self):  # E-I02
        self.assertEqual(self.gs.pos, self.maze.start)

    def test_initial_not_complete(self):  # E-I03
        self.assertFalse(self.gs.is_complete)

    def test_initial_not_dead(self):  # E-I04
        self.assertFalse(self.gs.is_dead)

    def test_npc_states_initialized(self):  # E-I05
        self.assertIn("old_weary", self.gs.npc_states)
        self.assertIn("messy_goblin", self.gs.npc_states)

    def test_npc_states_start_at_zero(self):  # E-I06
        for npc_id, ns in self.gs.npc_states.items():
            self.assertEqual(ns.emotional_state, 0, f"{npc_id} should start at 0")

    def test_fog_cleared_at_start(self):  # E-I07
        self.assertFalse(self.gs.is_fogged(self.maze.start))


# ===================================================================
# 2) Movement
# ===================================================================

class TestMovement(_EngineTestBase):
    """E-M01 ... E-M04"""

    def test_valid_move_changes_position(self):  # E-M01
        self._move_dir("e")
        self.assertEqual(self.gs.pos, Position(0, 1))

    def test_wall_blocks_movement(self):  # E-M02
        self._move_dir("e")  # to (0,1)
        self._move_dir("s")  # wall at (0,1) south
        self.assertEqual(self.gs.pos, Position(0, 1))

    def test_boundary_blocks_movement(self):  # E-M03
        self._move_dir("n")  # can't go north from (0,0)
        self.assertEqual(self.gs.pos, Position(0, 0))

    def test_move_count_increments(self):  # E-M04
        self._move_dir("e")  # valid
        self._move_dir("e")  # valid
        self._move_dir("n")  # blocked by boundary from (0,2) -- shouldn't increment
        self.assertEqual(self.gs.move_count, 2)

    def test_fog_cleared_on_move(self):  # E-M05
        self._move_dir("e")
        self.assertFalse(self.gs.is_fogged(Position(0, 1)))


# ===================================================================
# 3) NPC interactions
# ===================================================================

class TestNPCInteraction(_EngineTestBase):
    """E-N01 ... E-N10"""

    def test_kindness_no_npc_here(self):  # E-N01
        self.game._interact_npc("kind")
        # Should be a no-op (no crash, no state change)
        self.assertEqual(self.gs.pos, self.maze.start)

    def test_cruelty_no_npc_here(self):  # E-N02
        self.game._interact_npc("cruel")
        self.assertEqual(self.gs.pos, self.maze.start)

    def test_kindness_increases_emotion(self):  # E-N03
        # Move to Old Weary at (0,2)
        self._move_dir("e")
        self._move_dir("e")
        self.game._interact_npc("kind")
        ns = self.gs.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, 1)

    def test_cruelty_decreases_emotion(self):  # E-N04
        self._move_dir("e")
        self._move_dir("e")
        self.game._interact_npc("cruel")
        ns = self.gs.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, -1)

    def test_kind_then_cruel_causes_puzzled_reversal(self):  # E-N05
        self._move_dir("e")
        self._move_dir("e")
        self.game._interact_npc("kind")
        self.game._interact_npc("cruel")
        ns = self.gs.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, 1)
        self.assertTrue(ns.is_puzzled)

    def test_old_weary_cruel_to_minus_3_resolves(self):  # E-N06
        self._move_dir("e")
        self._move_dir("e")
        for _ in range(3):
            self.game._interact_npc("cruel")
        ns = self.gs.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, -3)
        self.assertTrue(ns.resolved)

    def test_old_weary_kind_to_plus_3_is_fail(self):  # E-N07
        self._move_dir("e")
        self._move_dir("e")
        for _ in range(3):
            self.game._interact_npc("kind")
        ns = self.gs.npc_states["old_weary"]
        self.assertTrue(ns.resolved)
        self.assertIn("fail", ns.resolution)

    def test_messy_goblin_kind_to_plus_3_resolves(self):  # E-N08
        # Messy Goblin at (2,1): S, E, S
        self._move_dir("s")
        self._move_dir("e")
        self._move_dir("s")
        for _ in range(3):
            self.game._interact_npc("kind")
        ns = self.gs.npc_states["messy_goblin"]
        self.assertEqual(ns.emotional_state, 3)
        self.assertTrue(ns.resolved)

    def test_messy_goblin_cruel_to_minus_3_is_fail(self):  # E-N09
        self._move_dir("s")
        self._move_dir("e")
        self._move_dir("s")
        for _ in range(3):
            self.game._interact_npc("cruel")
        ns = self.gs.npc_states["messy_goblin"]
        self.assertTrue(ns.resolved)
        self.assertIn("fail", ns.resolution)

    def test_resolved_npc_cant_interact(self):  # E-N10
        self._move_dir("e")
        self._move_dir("e")
        for _ in range(3):
            self.game._interact_npc("cruel")
        # NPC is resolved -- further interaction should be a no-op
        ns = self.gs.npc_states["old_weary"]
        old_count = ns.interaction_count
        self.game._interact_npc("kind")
        self.assertEqual(ns.interaction_count, old_count)


# ===================================================================
# 4) Win / lose conditions
# ===================================================================

class TestWinLose(_EngineTestBase):
    """E-W01 ... E-W04"""

    def test_exit_locked_without_npc_resolution(self):  # E-W01
        # Rush to exit (2,2) without resolving NPCs
        self._move_dir("s")
        self._move_dir("e")
        self._move_dir("s")
        self._move_dir("e")
        self.assertFalse(self.gs.is_complete)

    def test_exit_unlocked_with_both_resolved(self):  # E-W02
        # Resolve Old Weary (cruel x3 at (0,2))
        self._move_dir("e")
        self._move_dir("e")
        for _ in range(3):
            self.game._interact_npc("cruel")

        # Navigate to Messy Goblin at (2,1)
        self._move_dir("s")  # (1,2)
        self._move_dir("w")  # (1,1)
        self._move_dir("s")  # (2,1)
        for _ in range(3):
            self.game._interact_npc("kind")

        # Go to exit (2,2)
        self._move_dir("e")
        self.assertTrue(self.gs.is_complete)

    def test_all_npcs_resolved_method(self):  # E-W03
        self.assertFalse(self.gs.all_npcs_resolved())
        # Resolve both
        self._move_dir("e")
        self._move_dir("e")
        for _ in range(3):
            self.game._interact_npc("cruel")
        self._move_dir("s")
        self._move_dir("w")
        self._move_dir("s")
        for _ in range(3):
            self.game._interact_npc("kind")
        self.assertTrue(self.gs.all_npcs_resolved())

    def test_death_from_pit(self):  # E-W04
        self.gs.hp = 1
        self._move_dir("s")  # pit at (1,0)
        if self.gs.hp <= 0:
            self.assertTrue(self.gs.is_dead)


# ===================================================================
# 5) GameState unit tests
# ===================================================================

class TestGameState(unittest.TestCase):
    """E-GS01 ... E-GS05"""

    def setUp(self):
        self.maze = build_3x3_maze()
        from game import GameState
        self.gs = GameState(self.maze, seed=0)

    def test_fog_initially_covers_distant_cells(self):  # E-GS01
        # Cells far from start should be fogged
        self.assertTrue(self.gs.is_fogged(Position(2, 2)))

    def test_fog_clear_radius(self):  # E-GS02
        self.gs.clear_fog_radius(Position(1, 1), radius=1)
        self.assertFalse(self.gs.is_fogged(Position(1, 1)))

    def test_dungeon_map_has_floor(self):  # E-GS03
        # start cell should be '.'
        r, c = self.maze.start.row, self.maze.start.col
        self.assertEqual(self.gs.dungeon_map[r][c], ".")

    def test_npc_states_populated(self):  # E-GS04
        self.assertIn("old_weary", self.gs.npc_states)
        self.assertIn("messy_goblin", self.gs.npc_states)

    def test_consumed_items_tracking(self):  # E-GS05
        self.assertEqual(len(self.gs.consumed_potions), 0)
        self.assertEqual(len(self.gs.triggered_pits), 0)


# ===================================================================
# 6) Boundary enforcement
# ===================================================================

class TestBoundaries(unittest.TestCase):
    """E-B01 ... E-B02"""

    def test_main_imports_maze_and_db(self):  # E-B01
        src = (Path(__file__).parent / "main.py").read_text(encoding="utf-8")
        self.assertTrue(
            "from maze import" in src or "import maze" in src,
            "main.py must import maze",
        )
        self.assertTrue(
            "from db import" in src or "import db" in src,
            "main.py must import db",
        )

    def test_game_does_not_import_db_directly(self):  # E-B02
        src = (Path(__file__).parent / "game.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "db",
                        "game.py should not import db directly")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "db":
                    self.fail("game.py should not import from db directly")


if __name__ == "__main__":
    unittest.main()
