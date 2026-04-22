# CS504_TriviaMaze_WhiteForce

## Run the MVP (CLI — for grading)

### Windows (PowerShell)
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py main_cli.py

## Run the Visual Demo (Pygame)
py main.py


## AI Audit Reflection

I ran an AI code review with the prompt to act as a Senior Staff Engineer and evaluate strict separation of concerns across the codebase (domain/maze vs persistence/db vs engine/view). The AI reported no persistence leakage into the domain layer (maze remains pure), but it did flag that db.py contains some engine/game semantics—specifically, `top_scores()` sorts by `metrics["move_count"]`, and the repository interface includes NPC/dungeon-specific persistence methods that mirror gameplay concepts (e.g., `save_npc_state`, `get_npc_states`, `save_dungeon_layout`). The AI suggested simplifying persistence to store a single game-state snapshot and removing those NPC/dungeon-specific repository APIs to reduce coupling.

I chose to reject the refactor for the current MVP. I rejected it because we want to stabilize integration before changing peristence contracts: the integrated CLI MVP is the current priority and I want to minimize destabilizing changes during resubmission. The existing boundaries are currently understandable and enforceable (maze remains independent, persistence is accessed through the repo), and the suggested cleanup is a strong candidate for a future iteration once the MVP is stable and tests are updated to reflect the simplified snapshot contract.


---

## Docker Instructions (Assignment 2)

### Build the Image
From the repository root:
```bash
docker build -f Dockerfiles/Dockerfile -t maze .
