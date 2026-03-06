"""
view.py — CLI rendering helpers (NO I/O)

Rules:
- Must not call print() or input()
- Should not import maze.py or db.py
- Accepts plain data (dicts/lists/strings/ints) and returns strings
"""

def render_status_bar(v: dict) -> str:
    """Return a status bar string from a plain dict view."""
    parts = [f"HP {v.get('hp')}/{v.get('max_hp')}"]
    parts.append(f"Potions: {v.get('healing_potions')}")
    parts.append(f"Moves: {v.get('move_count')}")

    flags = []
    if v.get("portcullis_open"):
        flags.append("PORTCULLIS OPEN")
    if v.get("door_open"):
        flags.append("DOOR OPEN")
    if v.get("escape_impossible"):
        flags.append("!! ESCAPE IMPOSSIBLE !!")
    if flags:
        parts.append(" | ".join(flags))

    return "[" + " | ".join(parts) + "]"

def render_controls(v: dict) -> str:
    """Return the controls prompt string from a plain dict view."""
    controls = list(v.get("available_moves", []))
    if v.get("npc_here"):
        controls.extend(["K(indness)", "C(ruelty)"])
    controls.extend(["look", "heal", "save", "quit"])
    return "Controls: " + ", ".join(controls)