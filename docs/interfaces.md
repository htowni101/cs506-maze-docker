# Interfaces & Boundaries (Walking Skeleton)

This project is a modular CLI Quiz Maze game with strict boundaries:

- `maze.py` — Domain Logic (pure python, no I/O)
- `db.py` — Persistence (JSON I/O only)
- `main.py` — Engine/Orchestrator (wiring + CLI)

The walking skeleton supports:
- A minimal 3x3 maze
- Moving via CLI (N/S/E/W)
- Saving/loading state to JSON
- Boundary enforcement via interfaces

---

## Dependency Rules (Non-Negotiable)

### maze.py (Domain)
- MUST NOT import `db` or `main`
- MUST NOT use `print()` or `input()`
- May use: `dataclasses`, `enum`, `typing` and other stdlib utilities
- Output is **data only**, never text UI

### db.py (Persistence)
- MUST NOT import `maze` or `main`
- MUST store JSON-safe primitives only:
  - dict, list, str, int, float, bool, None
- Complex objects MUST be serialized (e.g., enums to strings)

### main.py (Engine)
- Only module allowed to import other modules (`maze`, `db`)
- Only module allowed to use `print()` and `input()`
- Responsible for translating between domain objects and JSON-safe DTOs

---

## Cross-Boundary Data

### Position (Domain Object)
`Position` is used within domain and engine.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Position:
    row: int
    col: int
``