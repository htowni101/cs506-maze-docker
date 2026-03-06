"""
test_maze_contract.py -- Maze Domain Contract Tests

Tests ONLY maze.py.  Validates public types, the 3x3 factory, the
procedural factory, build_dungeon_maze, and the architectural constraints.
"""
import ast
import unittest
from collections import deque
from pathlib import Path

from maze import (
    Direction,
    Position,
    CellKind,
    CellSpec,
    Maze,
    build_3x3_maze,
    build_square_maze,
    build_dungeon_maze,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bfs_reachable(maze: Maze, start: Position) -> set[Position]:
    """Return every Position reachable from *start* via available_moves."""
    visited: set[Position] = set()
    queue: deque[Position] = deque([start])
    visited.add(start)
    while queue:
        pos = queue.popleft()
        for d in maze.available_moves(pos):
            nb = pos.moved(d)
            if nb not in visited:
                try:
                    maze.cell(nb)
                    visited.add(nb)
                    queue.append(nb)
                except KeyError:
                    pass
    return visited


# ===================================================================
# 1) Type-level checks
# ===================================================================

class TestDirectionEnum(unittest.TestCase):
    """M-T01 ... M-T03"""

    def test_four_members(self):  # M-T01
        self.assertEqual(set(Direction), {Direction.N, Direction.S, Direction.E, Direction.W})

    def test_opposites(self):  # M-T02
        self.assertIs(Direction.N.opposite, Direction.S)
        self.assertIs(Direction.S.opposite, Direction.N)
        self.assertIs(Direction.E.opposite, Direction.W)
        self.assertIs(Direction.W.opposite, Direction.E)

    def test_deltas(self):  # M-T03
        self.assertEqual((Direction.N.dr, Direction.N.dc), (-1, 0))
        self.assertEqual((Direction.S.dr, Direction.S.dc), (1, 0))
        self.assertEqual((Direction.E.dr, Direction.E.dc), (0, 1))
        self.assertEqual((Direction.W.dr, Direction.W.dc), (0, -1))


class TestPosition(unittest.TestCase):
    """M-T04 ... M-T06"""

    def test_frozen_and_hashable(self):  # M-T04
        p = Position(0, 0)
        s = {p, Position(0, 0), Position(1, 1)}
        self.assertEqual(len(s), 2)
        with self.assertRaises(AttributeError):
            p.row = 5

    def test_moved(self):  # M-T05
        self.assertEqual(Position(1, 1).moved(Direction.N), Position(0, 1))
        self.assertEqual(Position(1, 1).moved(Direction.S), Position(2, 1))
        self.assertEqual(Position(1, 1).moved(Direction.E), Position(1, 2))
        self.assertEqual(Position(1, 1).moved(Direction.W), Position(1, 0))

    def test_to_dict_roundtrip(self):  # M-T06
        for pos in [Position(0, 0), Position(2, 2), Position(1, 1)]:
            self.assertEqual(Position.from_dict(pos.to_dict()), pos)


class TestCellKind(unittest.TestCase):
    """M-T07"""

    def test_three_members(self):
        self.assertEqual(
            {ck.value for ck in CellKind},
            {"START", "EXIT", "NORMAL"},
        )


class TestCellSpec(unittest.TestCase):
    """M-T08, M-T09"""

    def test_is_passable(self):  # M-T08
        spec = CellSpec(pos=Position(0, 0), blocked={Direction.N, Direction.W})
        self.assertFalse(spec.is_passable(Direction.N))
        self.assertFalse(spec.is_passable(Direction.W))
        self.assertTrue(spec.is_passable(Direction.S))
        self.assertTrue(spec.is_passable(Direction.E))

    def test_tile_type_default_none(self):  # M-T09
        spec = CellSpec(pos=Position(0, 0))
        self.assertIsNone(spec.tile_type)

    def test_tile_type_custom(self):  # M-T10
        spec = CellSpec(pos=Position(0, 0), tile_type="room")
        self.assertEqual(spec.tile_type, "room")


# ===================================================================
# 2) build_3x3_maze() contract
# ===================================================================

class TestBuild3x3Maze(unittest.TestCase):
    """M-301 ... M-313"""

    @classmethod
    def setUpClass(cls):
        cls.maze = build_3x3_maze()

    def test_dimensions(self):  # M-301
        self.assertEqual(self.maze.width, 3)
        self.assertEqual(self.maze.height, 3)

    def test_start_cell(self):  # M-302
        self.assertEqual(self.maze.start, Position(0, 0))
        self.assertEqual(self.maze.cell(Position(0, 0)).kind, CellKind.START)

    def test_exit_cell(self):  # M-303
        self.assertEqual(self.maze.exit, Position(2, 2))
        self.assertEqual(self.maze.cell(Position(2, 2)).kind, CellKind.EXIT)

    def test_nine_cells(self):  # M-304
        self.assertEqual(len(self.maze.all_positions()), 9)

    def test_two_npcs_placed(self):  # M-305
        npc_count = sum(
            1 for c in self.maze.all_cells() if c.npc_id is not None
        )
        self.assertEqual(npc_count, 2)

    def test_at_least_one_pit(self):  # M-306
        pit_count = sum(1 for c in self.maze.all_cells() if c.has_pit)
        self.assertGreaterEqual(pit_count, 1)

    def test_known_wall_01_south(self):  # M-307
        self.assertIn(Direction.S, self.maze.cell(Position(0, 1)).blocked)

    def test_walls_symmetric(self):  # M-308
        self.assertIn(Direction.N, self.maze.cell(Position(1, 1)).blocked)
        self.assertIn(Direction.W, self.maze.cell(Position(2, 1)).blocked)

    def test_available_moves_at_start(self):  # M-309
        moves = self.maze.available_moves(Position(0, 0))
        self.assertEqual(moves, {Direction.S, Direction.E})

    def test_next_pos_into_wall_is_none(self):  # M-310
        self.assertIsNone(self.maze.next_pos(Position(0, 1), Direction.S))

    def test_next_pos_valid(self):  # M-311
        self.assertEqual(
            self.maze.next_pos(Position(0, 0), Direction.E),
            Position(0, 1),
        )

    def test_exit_reachable(self):  # M-312
        reachable = _bfs_reachable(self.maze, self.maze.start)
        self.assertIn(self.maze.exit, reachable)

    def test_all_npcs_reachable(self):  # M-313
        reachable = _bfs_reachable(self.maze, self.maze.start)
        for cell in self.maze.all_cells():
            if cell.npc_id:
                self.assertIn(
                    cell.pos,
                    reachable,
                    f"NPC {cell.npc_id} at {cell.pos} is unreachable",
                )


# ===================================================================
# 3) build_square_maze(size, seed) contract
# ===================================================================

class TestBuildSquareMaze(unittest.TestCase):
    """M-S01 ... M-S07"""

    def test_dimensions(self):  # M-S01
        m = build_square_maze(5, seed=42)
        self.assertEqual(m.width, 5)
        self.assertEqual(m.height, 5)

    def test_start_position(self):  # M-S02
        m = build_square_maze(5, seed=42)
        self.assertEqual(m.start, Position(0, 0))

    def test_exit_position(self):  # M-S03
        m = build_square_maze(5, seed=42)
        self.assertEqual(m.exit, Position(4, 4))

    def test_deterministic(self):  # M-S04
        m1 = build_square_maze(5, seed=99)
        m2 = build_square_maze(5, seed=99)
        for pos in m1.all_positions():
            self.assertEqual(m1.cell(pos).blocked, m2.cell(pos).blocked)

    def test_different_seed_different_maze(self):  # M-S05
        m1 = build_square_maze(5, seed=1)
        m2 = build_square_maze(5, seed=2)
        walls1 = {pos: frozenset(m1.cell(pos).blocked) for pos in m1.all_positions()}
        walls2 = {pos: frozenset(m2.cell(pos).blocked) for pos in m2.all_positions()}
        self.assertNotEqual(walls1, walls2)

    def test_every_cell_reachable(self):  # M-S06
        m = build_square_maze(5, seed=42)
        reachable = _bfs_reachable(m, m.start)
        self.assertEqual(len(reachable), 25)

    def test_two_npcs_placed(self):  # M-S07
        m = build_square_maze(5, seed=42)
        npc_count = sum(1 for c in m.all_cells() if c.npc_id is not None)
        self.assertEqual(npc_count, 2)


# ===================================================================
# 4) build_dungeon_maze(seed) contract
# ===================================================================

class TestBuildDungeonMaze(unittest.TestCase):
    """M-D01 ... M-D10"""

    @classmethod
    def setUpClass(cls):
        cls.maze = build_dungeon_maze(seed=42)

    def test_has_cells(self):  # M-D01
        self.assertGreater(len(self.maze.all_cells()), 0)

    def test_start_is_passable(self):  # M-D02
        start = self.maze.cell(self.maze.start)
        self.assertEqual(start.kind, CellKind.START)

    def test_exit_is_passable(self):  # M-D03
        exit_cell = self.maze.cell(self.maze.exit)
        self.assertEqual(exit_cell.kind, CellKind.EXIT)

    def test_exit_reachable_from_start(self):  # M-D04
        reachable = _bfs_reachable(self.maze, self.maze.start)
        self.assertIn(self.maze.exit, reachable)

    def test_two_npcs_placed(self):  # M-D05
        npc_cells = [c for c in self.maze.all_cells() if c.npc_id is not None]
        self.assertEqual(len(npc_cells), 2)

    def test_npcs_reachable(self):  # M-D06
        reachable = _bfs_reachable(self.maze, self.maze.start)
        for cell in self.maze.all_cells():
            if cell.npc_id:
                self.assertIn(cell.pos, reachable, f"{cell.npc_id} unreachable")

    def test_deterministic(self):  # M-D07
        m2 = build_dungeon_maze(seed=42)
        cells1 = sorted(self.maze.all_positions(), key=lambda p: (p.row, p.col))
        cells2 = sorted(m2.all_positions(), key=lambda p: (p.row, p.col))
        self.assertEqual(cells1, cells2)

    def test_different_seed_different_layout(self):  # M-D08
        m2 = build_dungeon_maze(seed=99)
        pos1 = frozenset(self.maze.all_positions())
        pos2 = frozenset(m2.all_positions())
        self.assertNotEqual(pos1, pos2)

    def test_tile_types_present(self):  # M-D09
        tile_types = {c.tile_type for c in self.maze.all_cells() if c.tile_type}
        self.assertTrue(len(tile_types) > 0, "Dungeon cells should have tile_type set")

    def test_has_pits_or_potions(self):  # M-D10
        has_pit = any(c.has_pit for c in self.maze.all_cells())
        has_potion = any(
            c.has_healing_potion or c.has_vision_potion
            for c in self.maze.all_cells()
        )
        self.assertTrue(has_pit or has_potion, "Dungeon should have hazards/items")

    def test_maze_id_contains_seed(self):  # M-D11
        self.assertIn("42", self.maze.maze_id)


# ===================================================================
# 5) Constraint enforcement
# ===================================================================

class TestMazeConstraints(unittest.TestCase):
    """M-C01 ... M-C03"""

    @classmethod
    def setUpClass(cls):
        src = Path(__file__).parent / "maze.py"
        cls.source = src.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_no_import_db(self):  # M-C01
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "db")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "db")

    def test_no_import_main(self):  # M-C02
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "main")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "main")

    def test_no_print_calls(self):  # M-C03
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    self.fail("maze.py must not call print()")


if __name__ == "__main__":
    unittest.main()
