# RUNBOOK — The White Witch’s Labyrinth (Walking Skeleton)

This RUNBOOK defines the **operational contract** for the Walking Skeleton:

- Module dependency rules
- How to run the game (CLI)
- P0 (critical) tests required to call the skeleton “done”

This document is authoritative for Part 2 and Part 3 of the assignment.

---

## 1. Module Dependency Rules

Strict separation of concerns is mandatory.

### 1.1 maze.py — Domain Logic

**May import:**
- Standard library only (`dataclasses`, `typing`, `enum`, etc.)

**Must NOT import:**
- `db.py`
- `main.py`
- Any I/O or framework code

**Responsibilities:**
- Represent the maze grid (3×3 for skeleton)
- Track player position
- Validate and apply movement
- Expose state via domain objects
- Convert domain state to/from primitive representations if required by design

**Constraints:**
- No `print()` or `input()`
- No file access
- Outputs data only

---

### 1.2 db.py — Persistence Layer

**May import:**
- Standard library only (`json`, `pathlib`, `typing`, etc.)

**Must NOT import:**
- `maze.py`
- `main.py`

**Responsibilities:**
- Save game state to JSON
- Load game state from JSON
- Handle missing or corrupted save files gracefully

**Constraints:**
- Store **JSON‑safe primitives only**
- Convert dataclasses and enums to primitive forms
- `load()` returns `None` if no valid save exists

---

### 1.3 main.py — Engine / Controller

**May import:**
- `maze.py`
- `db.py`
- Standard library

**Responsibilities:**
- Composition root of the application
- Create and wire domain and persistence objects
- Run the CLI game loop
- Handle all user input and output
- Translate between domain objects and persistence DTOs
- Save state after meaningful changes
- Exit cleanly on user request

**Constraints:**
- Only module allowed to use `print()` and `input()`
- No domain rules implemented here

---

## 2. Direction of Dependencies

The allowed dependency direction is strictly one‑way:
