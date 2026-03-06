"""
main.py — Engine + CLI Wiring (The Orchestrator)

Initialises Maze, loads DB, and runs the input/output loop.

NPC Mechanics:
  - Two NPCs: Old Weary (lever guard) and Messy Goblin (door password holder).
  - K = Kindness (+1 emotional state), C = Cruelty (-1 emotional state).
  - Old Weary must reach -3 to leave → unlocks the portcullis lever.
  - Messy Goblin must reach +3 to reveal the door password.
  - Both conditions needed to exit.
  - Positive max (+3 for Old Weary / -3 for Messy Goblin) = NPC stays forever → ESCAPE IMPOSSIBLE.
  - Dungeon + controls redraw after every input.

CONSTRAINTS:
  - ONLY module allowed to import maze, db, and npc_data.
  - ONLY module allowed to use print() and input().
  - Enforces boundaries: maze never talks to db.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

import view

# --- Module imports (main.py is the ONLY place these happen) ---
from maze import (
    Maze,
    Position,
    Direction,
    CellKind,
    CellSpec,
    build_3x3_maze,
    build_square_maze,
)
from db import (
    GameRepository,    
    open_repo,        
)
from npc_data import (
    NPCState,
    NEGATIVE_SET,
    POSITIVE_SET,
    EMOTION_OPPOSITES,
    pick_action_and_category,
    pick_action_from_category,
    category_for_side,
    get_reaction,
    OLD_WEARY_GREETING,
    OLD_WEARY_DESCRIPTION,
    OLD_WEARY_CRUEL_ACTIONS,
    OLD_WEARY_KIND_ACTIONS,
    OLD_WEARY_CRUEL_REACTIONS,
    OLD_WEARY_KIND_REACTIONS,
    MESSY_GOBLIN_GREETING,
    MESSY_GOBLIN_DESCRIPTION,
    MESSY_GOBLIN_CRUEL_ACTIONS,
    MESSY_GOBLIN_KIND_ACTIONS,
    MESSY_GOBLIN_CRUEL_REACTIONS,
    MESSY_GOBLIN_KIND_REACTIONS,
    EMOTION_LABELS,
)


# ---------------------------------------------------------------------------
# NPC registry (maps npc_id → data)
# ---------------------------------------------------------------------------

NPC_REGISTRY: dict[str, dict] = {
    "old_weary": {
        "name": "Old Weary",
        "greeting": OLD_WEARY_GREETING,
        "description": OLD_WEARY_DESCRIPTION,
        "cruel_actions": OLD_WEARY_CRUEL_ACTIONS,
        "kind_actions": OLD_WEARY_KIND_ACTIONS,
        "cruel_reactions": OLD_WEARY_CRUEL_REACTIONS,
        "kind_reactions": OLD_WEARY_KIND_REACTIONS,
        # Old Weary must be driven away (cruel → -3)
        "win_direction": "cruel",     # player must be cruel to win
        "win_threshold": -3,
        "fail_threshold": 3,
    },
    "messy_goblin": {
        "name": "Messy Goblin",
        "greeting": MESSY_GOBLIN_GREETING,
        "description": MESSY_GOBLIN_DESCRIPTION,
        "cruel_actions": MESSY_GOBLIN_CRUEL_ACTIONS,
        "kind_actions": MESSY_GOBLIN_KIND_ACTIONS,
        "cruel_reactions": MESSY_GOBLIN_CRUEL_REACTIONS,
        "kind_reactions": MESSY_GOBLIN_KIND_REACTIONS,
        # Messy Goblin must be befriended (kind → +3)
        "win_direction": "kind",
        "win_threshold": 3,
        "fail_threshold": -3,
    },
}


# ---------------------------------------------------------------------------
# Serialisation helpers  (Position <-> dict at the boundary)
# ---------------------------------------------------------------------------

def _pos_to_dict(pos: Position) -> dict:
    return {"row": pos.row, "col": pos.col}


def _dict_to_pos(d: dict) -> Position:
    return Position(row=d["row"], col=d["col"])


def _state_to_json(state: "EngineState") -> dict:
    """Convert engine state to a JSON-safe dict for persistence."""
    return {
        "pos": _pos_to_dict(state.pos),
        "move_count": state.move_count,
        "hp": state.hp,
        "max_hp": state.max_hp,
        "healing_potions": state.healing_potions,
        "vision_potions": state.vision_potions,
        "npc_states": {k: v.to_dict() for k, v in state.npc_states.items()},
        "npc_greeted": list(state.npc_greeted),
        "visited": [_pos_to_dict(p) for p in state.visited],
        "is_complete": state.is_complete,
        "is_dead": state.is_dead,
        "escape_impossible": state.escape_impossible,
    }


def _json_to_state(d: dict) -> "EngineState":
    """Restore engine state from a JSON-safe dict."""
    return EngineState(
        pos=_dict_to_pos(d["pos"]),
        move_count=d["move_count"],
        hp=d["hp"],
        max_hp=d["max_hp"],
        healing_potions=d["healing_potions"],
        vision_potions=d["vision_potions"],
        npc_states={k: NPCState.from_dict(v) for k, v in d.get("npc_states", {}).items()},
        npc_greeted=set(d.get("npc_greeted", [])),
        visited={_dict_to_pos(p) for p in d.get("visited", [])},
        is_complete=d.get("is_complete", False),
        is_dead=d.get("is_dead", False),
        escape_impossible=d.get("escape_impossible", False),
    )


# ---------------------------------------------------------------------------
# Engine State
# ---------------------------------------------------------------------------

@dataclass
class EngineState:
    """Mutable game state owned by the engine."""
    pos: Position
    move_count: int = 0
    hp: int = 100
    max_hp: int = 100
    healing_potions: int = 0
    vision_potions: int = 0
    npc_states: dict[str, NPCState] = field(default_factory=dict)
    npc_greeted: set[str] = field(default_factory=set)
    visited: set[Position] = field(default_factory=set)
    is_complete: bool = False
    is_dead: bool = False
    escape_impossible: bool = False


# ---------------------------------------------------------------------------
# View / Output DTOs (what the CLI renderer receives)
# ---------------------------------------------------------------------------

@dataclass
class GameView:
    pos: dict                       # {"row": int, "col": int}
    cell_kind: str                  # "START" | "EXIT" | "NORMAL"
    available_moves: list[str]      # e.g. ["N", "E"]
    hp: int
    max_hp: int
    healing_potions: int
    vision_potions: int
    move_count: int
    is_complete: bool
    is_dead: bool
    npc_here: Optional[str] = None  # npc_id if an NPC is present
    npc_name: Optional[str] = None  # display name of NPC
    npc_emotion: Optional[int] = None
    escape_impossible: bool = False
    portcullis_open: bool = False
    door_open: bool = False
    map_text: Optional[str] = None


@dataclass
class GameOutput:
    view: GameView
    messages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

DIRECTION_ALIASES = {
    "n": Direction.N, "north": Direction.N,
    "s": Direction.S, "south": Direction.S,
    "e": Direction.E, "east": Direction.E,
    "w": Direction.W, "west": Direction.W,
}

@dataclass
class Command:
    verb: str
    args: list[str] = field(default_factory=list)


def parse_command(raw: str) -> Command:
    parts = raw.strip().lower().split()
    if not parts:
        return Command(verb="")
    verb = parts[0]
    args = parts[1:]
    # "go n" → verb="n"
    if verb == "go" and args:
        verb = args[0]
        args = args[1:]
    return Command(verb=verb, args=args)


# ---------------------------------------------------------------------------
# Game Engine (UI-agnostic)
# ---------------------------------------------------------------------------

class GameEngine:
    """
    Core game loop logic.  Accepts Commands, returns GameOutput.
    Never calls print() or input() itself — that is the CLI's job.

    Win condition:
      - Old Weary resolved at -3 (portcullis open) AND
      - Messy Goblin resolved at +3 (door open) AND
      - Player reaches the EXIT cell.
    """

    def __init__(
        self,
        maze: Maze,
        repo: GameRepository,
        player_id: str,
        game_id: str,
        state: Optional[EngineState] = None,
    ):
        self.maze = maze
        self.repo = repo
        self.player_id = player_id
        self.game_id = game_id

        if state is None:
            self.state = EngineState(pos=maze.start)
            self.state.visited.add(maze.start)
            # Initialise NPC states for every NPC in the maze
            for cell in maze.all_cells():
                if cell.npc_id:
                    self.state.npc_states[cell.npc_id] = NPCState(npc_id=cell.npc_id)
        else:
            self.state = state

    # --- convenience queries ---

    def _npc_here(self) -> Optional[str]:
        """Return the npc_id at the player's current cell, or None."""
        npc_id = self.maze.npc_at(self.state.pos)
        if npc_id is None:
            return None
        ns = self.state.npc_states.get(npc_id)
        if ns and ns.resolved:
            return None  # NPC has left / resolved
        return npc_id

    def _portcullis_open(self) -> bool:
        ns = self.state.npc_states.get("old_weary")
        if ns is None:
            return True  # no Old Weary in this maze
        return ns.resolved and ns.emotional_state == -3

    def _door_open(self) -> bool:
        ns = self.state.npc_states.get("messy_goblin")
        if ns is None:
            return True
        return ns.resolved and ns.emotional_state == 3

    def _check_escape_impossible(self) -> bool:
        """True if either NPC has been pushed to the fail state."""
        for npc_id, info in NPC_REGISTRY.items():
            ns = self.state.npc_states.get(npc_id)
            if ns and ns.resolved and ns.emotional_state == info["fail_threshold"]:
                return True
        return False

    # --- public API ---

    def view(self) -> GameView:
        cell = self.maze.cell(self.state.pos)
        moves = self.maze.available_moves(self.state.pos)
        npc_id = self._npc_here()
        npc_name = NPC_REGISTRY[npc_id]["name"] if npc_id else None
        npc_emotion = None
        if npc_id:
            ns = self.state.npc_states.get(npc_id)
            if ns:
                npc_emotion = ns.emotional_state
        return GameView(
            pos=_pos_to_dict(self.state.pos),
            cell_kind=cell.kind.value,
            available_moves=sorted(d.name for d in moves),
            hp=self.state.hp,
            max_hp=self.state.max_hp,
            healing_potions=self.state.healing_potions,
            vision_potions=self.state.vision_potions,
            move_count=self.state.move_count,
            is_complete=self.state.is_complete,
            is_dead=self.state.is_dead,
            npc_here=npc_id,
            npc_name=npc_name,
            npc_emotion=npc_emotion,
            escape_impossible=self.state.escape_impossible,
            portcullis_open=self._portcullis_open(),
            door_open=self._door_open(),
            map_text=self._render_map(),
        )

    def handle(self, cmd: Command) -> GameOutput:
        messages: list[str] = []

        if self.state.is_complete:
            messages.append("You already won! Type 'quit' to exit.")
            return GameOutput(view=self.view(), messages=messages)

        if self.state.is_dead:
            messages.append("You are dead. Type 'quit' to exit.")
            return GameOutput(view=self.view(), messages=messages)

        verb = cmd.verb

        # Movement
        if verb in DIRECTION_ALIASES:
            direction = DIRECTION_ALIASES[verb]
            dest = self.maze.next_pos(self.state.pos, direction)
            if dest is None:
                messages.append(f"You can't go {direction.name} — wall!")
            else:
                self.state.pos = dest
                self.state.move_count += 1
                self.state.visited.add(dest)
                messages.append(f"Moved {direction.name}.")
                messages.extend(self._on_enter_cell(dest))

        # Kindness
        elif verb == "k" or verb == "kindness":
            messages.extend(self._interact_npc("kind"))

        # Cruelty
        elif verb == "c" or verb == "cruelty":
            messages.extend(self._interact_npc("cruel"))

        elif verb == "look":
            cell = self.maze.cell(self.state.pos)
            messages.append(f"You are at ({cell.pos.row},{cell.pos.col}) [{cell.kind.value}].")
            moves = self.maze.available_moves(self.state.pos)
            messages.append(f"Exits: {', '.join(d.name for d in sorted(moves, key=lambda d: d.name))}")
            npc_id = self._npc_here()
            if npc_id:
                info = NPC_REGISTRY[npc_id]
                messages.append(f"\n{info['description']}")

        elif verb == "map":
            messages.append(self._render_map())

        elif verb == "heal" or verb == "h":
            if self.state.healing_potions > 0:
                import random
                heal = random.randint(5, 15)
                self.state.hp = min(self.state.hp + heal, self.state.max_hp)
                self.state.healing_potions -= 1
                messages.append(f"Healed {heal} HP! (HP: {self.state.hp}/{self.state.max_hp})")
            else:
                messages.append("No healing potions!")

        elif verb == "save":
            self._persist()
            messages.append("Game saved.")

        elif verb == "quit" or verb == "q":
            self._persist()
            messages.append("__QUIT__")

        elif verb == "":
            pass  # empty input

        else:
            messages.append(
                f"Unknown command: {verb!r}. "
                "Try N/S/E/W, K(indness), C(ruelty), look, map, heal, save, quit."
            )

        return GameOutput(view=self.view(), messages=messages)

    # --- NPC interaction ---

    def _interact_npc(self, mode: str) -> list[str]:
        """Process a K or C action.  mode is 'kind' or 'cruel'.

        Reversal logic
        ──────────────
        When the player's action opposes the NPC's current emotional
        direction (e.g. K when emotional_state < 0), the emotion thread
        is preserved — we keep ``last_emotion_category`` instead of
        picking a new random one.  Emotion categories have opposites:

            anger ↔ happy,  sadness ↔ peaceful,
            fear  ↔ platonic_love,  disgust ↔ romantic_attraction

        When the NPC passes through 0 while reversing, the category
        flips to its opposite and a "[NPC] is puzzled." message is
        shown.  The player can bounce back and forth freely until the
        NPC hits -3 or +3 and becomes resolved.
        """
        msgs: list[str] = []
        npc_id = self._npc_here()
        if npc_id is None:
            msgs.append("There's no one here to interact with.")
            return msgs

        info = NPC_REGISTRY[npc_id]
        ns = self.state.npc_states[npc_id]
        old_state = ns.emotional_state

        # Is the player pushing *against* the direction they came from?
        # This includes being AT 0 when the last category is set (just
        # crossed through 0 and continuing the reversal).
        is_reversing = bool(ns.last_emotion_category) and (
            (old_state < 0 and mode == "kind") or
            (old_state > 0 and mode == "cruel") or
            (old_state == 0 and ns.last_emotion_category
             and (
                 (mode == "kind" and ns.last_emotion_category in NEGATIVE_SET) or
                 (mode == "cruel" and ns.last_emotion_category in POSITIVE_SET)
             ))
        )

        # ── Choose action text + category ──
        if is_reversing and ns.last_emotion_category:
            # Keep the existing emotion thread — pick action from the
            # opposite-side category so the text matches the new action.
            if mode == "kind":
                action_cat = category_for_side(ns.last_emotion_category, want_positive=True)
                action_text = pick_action_from_category(info["kind_actions"], action_cat)
            else:
                action_cat = category_for_side(ns.last_emotion_category, want_positive=False)
                action_text = pick_action_from_category(info["cruel_actions"], action_cat)
            # category thread stays as-is (it will be flipped for
            # reaction lookup below when on the opposite side)
        else:
            # Going deeper or starting from 0 — pick a fresh random category.
            if mode == "kind":
                category, action_text = pick_action_and_category(info["kind_actions"])
            else:
                category, action_text = pick_action_and_category(info["cruel_actions"])
            ns.last_emotion_category = category

        # ── Apply the emotional shift ──
        if mode == "kind":
            ns.apply_kindness()
        else:
            ns.apply_cruelty()

        msgs.append(f"\n{action_text}")

        # ── Determine NPC reaction ──
        new_state = ns.emotional_state
        intensity = abs(new_state)

        if new_state == 0:
            # Crossed through the midpoint — NPC is confused.
            npc_name = info["name"]
            msgs.append(f"\n{npc_name} is puzzled.")
        elif intensity > 0:
            # Map the stored thread to the correct side's category.
            if new_state > 0:
                reaction_cat = category_for_side(ns.last_emotion_category, want_positive=True)
                reaction = get_reaction(info["kind_reactions"], reaction_cat, intensity)
            else:
                reaction_cat = category_for_side(ns.last_emotion_category, want_positive=False)
                reaction = get_reaction(info["cruel_reactions"], reaction_cat, intensity)
            if reaction:
                msgs.append(f"\n{reaction}")

        # ── Check if NPC is now resolved ──
        if abs(new_state) >= 3 and not ns.resolved:
            ns.resolved = True
            if new_state == info["win_threshold"]:
                ns.resolution = f"{mode}_success"
            elif new_state == info["fail_threshold"]:
                ns.resolution = f"{mode}_fail"
                self.state.escape_impossible = True

        return msgs

    # --- internal ---

    def _on_enter_cell(self, pos: Position) -> list[str]:
        """Side-effects when stepping on a cell.  Returns messages."""
        msgs: list[str] = []
        cell = self.maze.cell(pos)

        # Pit damage
        if cell.has_pit:
            import random
            dmg = random.randint(1, 20)
            self.state.hp -= dmg
            msgs.append(f"You fell in a pit! -{dmg} HP")
            if self.state.hp <= 0:
                self.state.hp = 0
                self.state.is_dead = True
                msgs.append("You died!")
                return msgs

        # Pick up potion
        if cell.has_healing_potion:
            self.state.healing_potions += 1
            msgs.append("Found a healing potion!")

        if cell.has_vision_potion:
            self.state.vision_potions += 1
            msgs.append("Found a vision potion!")

        # NPC greeting (first visit only)
        npc_id = self._npc_here()
        if npc_id and npc_id not in self.state.npc_greeted:
            self.state.npc_greeted.add(npc_id)
            info = NPC_REGISTRY[npc_id]
            msgs.append(f"\n{info['greeting']}")

        # Exit check
        if cell.kind == CellKind.EXIT:
            if self.state.escape_impossible:
                msgs.append("The exit is sealed. ESCAPE IS IMPOSSIBLE.")
            elif self._portcullis_open() and self._door_open():
                self.state.is_complete = True
                msgs.append("*** YOU WIN! ***")
                self._record_score()
            else:
                blockers = []
                if not self._portcullis_open():
                    blockers.append("the portcullis is still locked (Old Weary guards the lever)")
                if not self._door_open():
                    blockers.append("you don't have the door password (Messy Goblin knows it)")
                msgs.append(f"Exit blocked — {' and '.join(blockers)}.")

        return msgs

    def _persist(self) -> None:
        state_dict = _state_to_json(self.state)
        status = "completed" if self.state.is_complete else "in_progress"
        self.repo.save_game(self.game_id, state_dict, status)

    def _record_score(self) -> None:
        self.repo.record_score(
            player_id=self.player_id,
            game_id=self.game_id,
            maze_id=self.maze.maze_id,
            maze_version=self.maze.maze_version,
            metrics={
                "move_count": self.state.move_count,
                "hp_remaining": self.state.hp,
            },
        )
        self._persist()

    def _render_map(self) -> str:
        """
        ASCII fog-of-war map.  Visited cells show their type; unvisited
        cells show '###'.  Player position shown as '@'.
        NPC cells show 'W' (Old Weary) or 'G' (Messy Goblin).
        """
        lines: list[str] = []
        for r in range(self.maze.height):
            row_parts: list[str] = []
            for c in range(self.maze.width):
                pos = Position(r, c)
                if pos == self.state.pos:
                    row_parts.append(" @ ")
                elif pos not in self.state.visited:
                    row_parts.append("###")
                else:
                    cell = self.maze.cell(pos)
                    if cell.kind == CellKind.START:
                        row_parts.append(" S ")
                    elif cell.kind == CellKind.EXIT:
                        row_parts.append(" X ")
                    elif cell.npc_id == "old_weary":
                        ns = self.state.npc_states.get("old_weary")
                        if ns and ns.resolved:
                            row_parts.append(" L ")  # lever left behind
                        else:
                            row_parts.append(" W ")
                    elif cell.npc_id == "messy_goblin":
                        ns = self.state.npc_states.get("messy_goblin")
                        if ns and ns.resolved:
                            row_parts.append(" . ")  # goblin left
                        else:
                            row_parts.append(" G ")
                    elif cell.has_pit:
                        row_parts.append(" O ")
                    else:
                        row_parts.append(" . ")
            lines.append("|".join(row_parts))
        header = f"  {'   '.join(str(c) for c in range(self.maze.width))}"
        result_lines = [header]
        for r, line in enumerate(lines):
            result_lines.append(f"{r} {line}")
        return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------

def _render_status_bar(v: GameView) -> str:
    """Build the status bar string."""
    parts = [f"HP {v.hp}/{v.max_hp}"]
    parts.append(f"Potions: {v.healing_potions}")
    parts.append(f"Moves: {v.move_count}")

    flags = []
    if v.portcullis_open:
        flags.append("PORTCULLIS OPEN")
    if v.door_open:
        flags.append("DOOR OPEN")
    if v.escape_impossible:
        flags.append("!! ESCAPE IMPOSSIBLE !!")
    if flags:
        parts.append(" | ".join(flags))

    return "[" + " | ".join(parts) + "]"


def _render_controls(v: GameView) -> str:
    """Build the controls prompt."""
    controls = list(v.available_moves)
    if v.npc_here:
        controls.extend(["K(indness)", "C(ruelty)"])
    controls.extend(["look", "heal", "save", "quit"])
    return "Controls: " + ", ".join(controls)


def _print_output(output: GameOutput) -> bool:
    """Print messages + full redraw.  Return True if game should quit."""
    quit_flag = False
    for msg in output.messages:
        if msg == "__QUIT__":
            print("Goodbye!")
            return True
        print(msg)

    v = output.view

    # Always show map + status + controls
    if v.map_text:
        print()
        print(v.map_text)
    print()
    print(view.render_status_bar(v.__dict__))

    if v.npc_here and v.npc_name:
        emotion_bar = "=" * max(0, v.npc_emotion + 3) if v.npc_emotion is not None else ""
        emotion_val = v.npc_emotion if v.npc_emotion is not None else 0
        print(f"{v.npc_name} is here.  Mood: [{emotion_val:+d}] {'█' * max(0, emotion_val + 3)}{'░' * max(0, 3 - emotion_val)}")

    print(view.render_controls(v.__dict__))
    return False


def run_cli(maze: Optional[Maze] = None, db_path: str = "game_data.db") -> None:
    """
    Main CLI loop.  Wires maze + db + engine, then reads input / prints output.
    Redraws dungeon and controls after every input.
    """
    if maze is None:
        maze = build_3x3_maze()

    repo = open_repo(db_path)

    # Player setup
    print("=== Isometric Dungeon — MVP ===")
    handle = input("Enter your name: ").strip() or "Hero"
    player = repo.get_or_create_player(handle)

    # Create a new game
    initial_state = _state_to_json(EngineState(pos=maze.start, visited={maze.start}))
    game_rec = repo.create_game(
        player_id=player.id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )

    engine = GameEngine(
        maze=maze,
        repo=repo,
        player_id=player.id,
        game_id=game_rec.id,
    )

    # Initial redraw
    output = engine.handle(parse_command("look"))
    _print_output(output)

    # Main loop — redraw after every input
    while True:
        try:
            raw = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            raw = "quit"
        cmd = parse_command(raw)
        output = engine.handle(cmd)
        if _print_output(output):
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_cli()
