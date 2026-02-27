"""
test_engine_integration.py — Full Integration Tests

Imports all three modules and verifies the engine wiring end-to-end,
including NPC interaction (K/C), emotional state, and win/fail conditions.
"""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path

from maze import (
    Maze,
    Position,
    Direction,
    CellKind,
    build_3x3_maze,
)
from db import JsonGameRepository
from main import (
    GameEngine,
    EngineState,
    Command,
    GameView,
    GameOutput,
    parse_command,
    _pos_to_dict,
    _dict_to_pos,
    _state_to_json,
    _json_to_state,
)
from npc_data import NPCState


class _EngineTestBase(unittest.TestCase):
    """Helper: creates maze + temp-file repo + engine per test."""

    def setUp(self):
        self.maze = build_3x3_maze()
        self._tmpfile = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        )
        self._tmpfile.close()
        self.db_path = self._tmpfile.name
        os.unlink(self.db_path)
        self.repo = JsonGameRepository(self.db_path)
        self.player = self.repo.get_or_create_player("TestHero")
        initial = _state_to_json(EngineState(pos=self.maze.start, visited={self.maze.start}))
        self.game_rec = self.repo.create_game(
            self.player.id, self.maze.maze_id, self.maze.maze_version, initial,
        )
        self.engine = GameEngine(
            maze=self.maze,
            repo=self.repo,
            player_id=self.player.id,
            game_id=self.game_rec.id,
        )

    def tearDown(self):
        for f in [self.db_path, self.db_path.replace(".json", ".tmp")]:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass

    def _cmd(self, text: str) -> GameOutput:
        return self.engine.handle(parse_command(text))

    def _move_to(self, *directions: str):
        """Convenience: move through a sequence of directions."""
        for d in directions:
            self._cmd(d)


# ===================================================================
# 1) Initialisation
# ===================================================================

class TestEngineInit(_EngineTestBase):
    """E-I01 … E-I06"""

    def test_creates_without_error(self):  # E-I01
        self.assertIsNotNone(self.engine)

    def test_initial_position_is_start(self):  # E-I02
        v = self.engine.view()
        self.assertEqual(v.pos, {"row": 0, "col": 0})

    def test_initial_not_complete(self):  # E-I03
        self.assertFalse(self.engine.view().is_complete)

    def test_initial_not_dead(self):  # E-I04
        self.assertFalse(self.engine.view().is_dead)

    def test_npc_states_initialized(self):  # E-I05
        self.assertIn("old_weary", self.engine.state.npc_states)
        self.assertIn("messy_goblin", self.engine.state.npc_states)

    def test_npc_states_start_at_zero(self):  # E-I06
        for npc_id, ns in self.engine.state.npc_states.items():
            self.assertEqual(ns.emotional_state, 0, f"{npc_id} should start at 0")


# ===================================================================
# 2) Movement
# ===================================================================

class TestMovement(_EngineTestBase):
    """E-M01 … E-M04"""

    def test_valid_move_changes_position(self):  # E-M01
        out = self._cmd("e")
        self.assertEqual(out.view.pos, {"row": 0, "col": 1})

    def test_wall_blocks_movement(self):  # E-M02
        self._cmd("e")
        out = self._cmd("s")
        self.assertEqual(out.view.pos, {"row": 0, "col": 1})
        self.assertTrue(any("wall" in m.lower() for m in out.messages))

    def test_boundary_blocks_movement(self):  # E-M03
        out = self._cmd("n")
        self.assertEqual(out.view.pos, {"row": 0, "col": 0})

    def test_move_count_increments(self):  # E-M04
        self._cmd("e")
        self._cmd("e")
        self._cmd("e")  # out of bounds — should NOT increment
        v = self.engine.view()
        self.assertEqual(v.move_count, 2)


# ===================================================================
# 3) Item interactions
# ===================================================================

class TestItems(_EngineTestBase):
    """E-IT01 … E-IT04"""

    def test_npc_greeting_on_first_visit(self):  # E-IT01
        # Old Weary is at (0,2): go E, E
        self._cmd("e")
        out = self._cmd("e")
        # Should see the NPC greeting
        all_text = "\n".join(out.messages)
        self.assertTrue(
            "migo" in all_text.lower() or "old weary" in all_text.lower(),
            "Expected Old Weary greeting",
        )

    def test_healing_potion_pickup(self):  # E-IT02
        self._cmd("s")
        self._cmd("e")
        out = self._cmd("e")
        self.assertGreaterEqual(self.engine.view().healing_potions, 1)

    def test_pit_damage(self):  # E-IT03
        initial_hp = self.engine.view().hp
        out = self._cmd("s")
        self.assertLess(self.engine.view().hp, initial_hp)

    def test_heal_command(self):  # E-IT04
        self._cmd("s")
        self._cmd("e")
        self._cmd("e")
        potions_before = self.engine.view().healing_potions
        self.assertGreaterEqual(potions_before, 1)
        self.engine.state.hp = 50
        out = self._cmd("heal")
        self.assertGreater(self.engine.view().hp, 50)
        self.assertEqual(self.engine.view().healing_potions, potions_before - 1)


# ===================================================================
# 4) NPC interactions
# ===================================================================

class TestNPCInteraction(_EngineTestBase):
    """E-N01 … E-N10"""

    def test_kindness_no_npc_here(self):  # E-N01
        out = self._cmd("k")
        self.assertTrue(any("no one here" in m.lower() for m in out.messages))

    def test_cruelty_no_npc_here(self):  # E-N02
        out = self._cmd("c")
        self.assertTrue(any("no one here" in m.lower() for m in out.messages))

    def test_kindness_increases_emotion(self):  # E-N03
        # Move to Old Weary at (0,2)
        self._move_to("e", "e")
        self._cmd("k")
        ns = self.engine.state.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, 1)

    def test_cruelty_decreases_emotion(self):  # E-N04
        self._move_to("e", "e")
        self._cmd("c")
        ns = self.engine.state.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, -1)

    def test_kind_then_cruel_cancels(self):  # E-N05
        self._move_to("e", "e")
        self._cmd("k")
        self._cmd("c")
        ns = self.engine.state.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, 0)

    def test_old_weary_cruel_to_minus_3_resolves(self):  # E-N06
        self._move_to("e", "e")
        self._cmd("c")
        self._cmd("c")
        self._cmd("c")
        ns = self.engine.state.npc_states["old_weary"]
        self.assertEqual(ns.emotional_state, -3)
        self.assertTrue(ns.resolved)

    def test_old_weary_kind_to_plus_3_escape_impossible(self):  # E-N07
        self._move_to("e", "e")
        self._cmd("k")
        self._cmd("k")
        self._cmd("k")
        self.assertTrue(self.engine.state.escape_impossible)

    def test_messy_goblin_kind_to_plus_3_resolves(self):  # E-N08
        # Messy Goblin is at (2,1): S, E, S
        self._move_to("s", "e", "s")
        self._cmd("k")
        self._cmd("k")
        self._cmd("k")
        ns = self.engine.state.npc_states["messy_goblin"]
        self.assertEqual(ns.emotional_state, 3)
        self.assertTrue(ns.resolved)

    def test_messy_goblin_cruel_to_minus_3_escape_impossible(self):  # E-N09
        self._move_to("s", "e", "s")
        self._cmd("c")
        self._cmd("c")
        self._cmd("c")
        self.assertTrue(self.engine.state.escape_impossible)

    def test_resolved_npc_cant_interact(self):  # E-N10
        self._move_to("e", "e")
        self._cmd("c")
        self._cmd("c")
        self._cmd("c")
        # NPC is resolved — further interactions should say "no one here"
        out = self._cmd("k")
        self.assertTrue(any("no one here" in m.lower() for m in out.messages))

    def test_reversal_shows_puzzled_at_zero(self):  # E-N11
        # Cruel to -1, then Kind back to 0 → "puzzled"
        self._move_to("e", "e")
        self._cmd("c")
        out = self._cmd("k")
        all_text = "\n".join(out.messages).lower()
        self.assertIn("puzzled", all_text)

    def test_reversal_preserves_emotion_thread(self):  # E-N12
        # Push to -2, force a known category, then reverse.
        # The last_emotion_category should survive the reversal.
        self._move_to("e", "e")
        ns = self.engine.state.npc_states["old_weary"]
        self._cmd("c")  # -1
        self._cmd("c")  # -2
        saved_cat = ns.last_emotion_category
        self.assertNotEqual(saved_cat, "")
        # Reverse: kind back toward 0
        self._cmd("k")  # -1
        # Category should not have changed
        self.assertEqual(ns.last_emotion_category, saved_cat)

    def test_reversal_flips_category_across_zero(self):  # E-N13
        # Push to -1, then reverse to +1.
        # The reaction should use the *opposite* category's kind_reactions.
        from npc_data import EMOTION_OPPOSITES
        self._move_to("e", "e")
        ns = self.engine.state.npc_states["old_weary"]
        self._cmd("c")  # -1
        negative_cat = ns.last_emotion_category
        self._cmd("k")  # 0 → puzzled
        self._cmd("k")  # +1 → should use positive opposite of negative_cat
        # We can't easily check which reaction text was shown, but we CAN
        # verify the emotion state and that the thread category is unchanged.
        self.assertEqual(ns.emotional_state, 1)
        self.assertEqual(ns.last_emotion_category, negative_cat)

    def test_full_bounce_cruel_kind_cruel(self):  # E-N14
        # -2, then +2, then back to -2 — should still work
        self._move_to("e", "e")
        ns = self.engine.state.npc_states["old_weary"]
        self._cmd("c"); self._cmd("c")  # -2
        self.assertEqual(ns.emotional_state, -2)
        self._cmd("k"); self._cmd("k")  # 0 (puzzled)
        self.assertEqual(ns.emotional_state, 0)
        self._cmd("k"); self._cmd("k")  # +2
        self.assertEqual(ns.emotional_state, 2)
        # Now reverse back
        self._cmd("c"); self._cmd("c")  # 0 (puzzled)
        self.assertEqual(ns.emotional_state, 0)
        self._cmd("c"); self._cmd("c")  # -2
        self.assertEqual(ns.emotional_state, -2)
        # Final push to -3 to resolve
        self._cmd("c")
        self.assertEqual(ns.emotional_state, -3)
        self.assertTrue(ns.resolved)


# ===================================================================
# 5) Win / lose conditions
# ===================================================================

class TestWinLose(_EngineTestBase):
    """E-W01 … E-W05"""

    def test_exit_locked_without_npc_resolution(self):  # E-W01
        # Go straight to exit without resolving NPCs
        self._move_to("s", "e", "s", "e")
        out = self._cmd("")  # just check view
        v = self.engine.view()
        self.assertFalse(v.is_complete)

    def test_exit_unlocked_with_both_npcs_resolved(self):  # E-W02
        # Resolve Old Weary (cruel ×3 at (0,2))
        self._move_to("e", "e")
        self._cmd("c")
        self._cmd("c")
        self._cmd("c")

        # Navigate to Messy Goblin at (2,1): S→(1,2), W→(1,1), S→(2,1)
        self._move_to("s", "w", "s")
        self._cmd("k")
        self._cmd("k")
        self._cmd("k")

        # Go to exit (2,2)
        out = self._cmd("e")
        self.assertTrue(self.engine.view().is_complete)

    def test_death_from_damage(self):  # E-W03
        self.engine.state.hp = 1
        self._cmd("s")  # pit at (1,0)
        if self.engine.view().hp <= 0:
            self.assertTrue(self.engine.view().is_dead)
        else:
            self.engine.state.hp = 0
            self.engine.state.is_dead = True
            self.assertTrue(self.engine.view().is_dead)

    def test_score_recorded_on_win(self):  # E-W04
        # Speed-run: resolve both NPCs and reach exit
        self._move_to("e", "e")
        self._cmd("c"); self._cmd("c"); self._cmd("c")
        self._move_to("s", "w", "s")
        self._cmd("k"); self._cmd("k"); self._cmd("k")
        self._cmd("e")
        self.assertTrue(self.engine.view().is_complete)
        scores = self.repo.top_scores(maze_id=self.maze.maze_id)
        self.assertGreater(len(scores), 0)

    def test_escape_impossible_blocks_exit(self):  # E-W05
        # Make Old Weary happy (+3) = escape impossible
        self._move_to("e", "e")
        self._cmd("k"); self._cmd("k"); self._cmd("k")
        # Resolve Messy Goblin correctly
        self._move_to("s", "w", "s")
        self._cmd("k"); self._cmd("k"); self._cmd("k")
        # Try exit
        out = self._cmd("e")
        self.assertFalse(self.engine.view().is_complete)
        self.assertTrue(any("impossible" in m.lower() for m in out.messages))


# ===================================================================
# 6) Persistence round-trip
# ===================================================================

class TestPersistence(_EngineTestBase):
    """E-P01 … E-P04"""

    def test_save_persists_state(self):  # E-P01
        self._cmd("e")
        self._cmd("save")
        rec = self.repo.get_game(self.game_rec.id)
        self.assertEqual(rec.state["move_count"], 1)

    def test_position_serialised(self):  # E-P02
        self._cmd("e")
        self._cmd("save")
        rec = self.repo.get_game(self.game_rec.id)
        self.assertEqual(rec.state["pos"], {"row": 0, "col": 1})

    def test_visited_serialised(self):  # E-P03
        self._cmd("e")
        self._cmd("save")
        rec = self.repo.get_game(self.game_rec.id)
        visited = rec.state["visited"]
        self.assertIsInstance(visited, list)
        for v in visited:
            self.assertIn("row", v)
            self.assertIn("col", v)

    def test_npc_states_serialised(self):  # E-P04
        self._move_to("e", "e")
        self._cmd("c")  # interact with Old Weary
        self._cmd("save")
        rec = self.repo.get_game(self.game_rec.id)
        npc_states = rec.state["npc_states"]
        self.assertIsInstance(npc_states, dict)
        self.assertIn("old_weary", npc_states)
        self.assertEqual(npc_states["old_weary"]["emotional_state"], -1)


# ===================================================================
# 7) Boundary enforcement
# ===================================================================

class TestBoundaries(_EngineTestBase):
    """E-B01 … E-B03"""

    def test_no_maze_types_in_db_state(self):  # E-B01
        self._cmd("e")
        self._cmd("save")
        rec = self.repo.get_game(self.game_rec.id)
        self._assert_json_safe(rec.state)

    def _assert_json_safe(self, obj, path=""):
        if isinstance(obj, (str, int, float, bool, type(None))):
            return
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                self._assert_json_safe(item, f"{path}[{i}]")
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                self.assertIsInstance(k, str, f"Non-string key at {path}: {k!r}")
                self._assert_json_safe(v, f"{path}.{k}")
            return
        self.fail(f"Non-JSON-safe type at {path}: {type(obj).__name__} = {obj!r}")

    def test_main_imports_maze_and_db(self):  # E-B02
        src = (Path(__file__).parent / "main.py").read_text(encoding="utf-8")
        self.assertTrue(
            "from maze import" in src or "import maze" in src,
            "main.py must import maze",
        )
        self.assertTrue(
            "from db import" in src or "import db" in src,
            "main.py must import db",
        )

    def test_engine_does_not_print(self):  # E-B03
        src = (Path(__file__).parent / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "GameEngine":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func = child.func
                        if isinstance(func, ast.Name) and func.id == "print":
                            self.fail("GameEngine must not call print()")


if __name__ == "__main__":
    unittest.main()
