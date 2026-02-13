# Olga Chadwell's The White Witch's Labyrinth

## Section A: The Theme (The Hook)

The game is set in **the Labyrinth** — a magical, shifting maze suspended between light and shadow. The atmosphere is ancient and uneasy: corridors twist and sometimes change, safe zones offer brief respite beside glowing crystals, and hazards (traps, water, corrupted creatures) force constant choices. Rooms and cells can contain enemies, traps, water to freeze into bridges, light crystals, and moral choice points where the player must decide how to respond.

**Why the player is here:** The White Witch is the **Guardian of Balance**. She must traverse the labyrinth to restore balance, reach a goal, or escape — the exact objective can be tuned per narrative. She cannot attack directly; she can only influence outcomes with limited magic. Her presence in the maze is both duty and trial.

**Main Character: The White Witch — Core Traits**

- Ancient but mortal.
- Guardian of balance.
- Magic tied to life force (limited energy pool).
- Cannot attack directly — only influence outcomes.

**Core Powers (Limited Resource-Based)**

- **Freeze:** Temporarily immobilizes enemies; can freeze traps to disable them; can freeze water to create bridges. Cost: Medium energy.
- **Heal:** Restore health to allies; calm corrupted creatures (partial redemption); revive fallen spirit companions (rare). Cost: High energy.

**Energy system:** Energy regenerates slowly over time or through specific sources: **light crystals** (one-time or limited pickups), **safe zones** (regen while standing in them), **sacrifice of movement speed** (e.g., moving slowly refills energy), and **moral decisions** (certain choices may grant or cost energy). Implementation will define exact values and trade-offs so the player must manage a finite resource across exploration and encounters.

### Possible Mechanics

- **Moving walls:** The layout changes over time or when triggered (e.g., in the Living Maze), so paths can open or close and the player must adapt.
- **Shadow creatures:** Hostile or neutral entities that inhabit the maze and react to the Witch's presence and choices.
- **Moral encounters:** At key moments the player chooses whether to **Freeze** (control) or **Heal** (restore). The choice affects outcomes, tone, and sometimes long-term consequences (allies, corruption level).
- **Time-based corruption:** Corruption spreads through corridors over time, adding pressure to progress and potentially blocking or altering paths if the player lingers too long.

### Areas (Ice Caverns, Ruined Temple, Living Maze, Mirror Hall)

The Labyrinth is divided into distinct zones the Witch traverses:

- **Ice Caverns:** A cold, crystalline region where Freeze may interact with the environment in special ways (e.g., extending bridges, sealing cracks).
- **Ruined Temple:** A fallen sacred space; may host Lost Children, light crystals, and moral encounters.
- **Living Maze:** Walls breathe and shift here; moving-wall mechanics are central. Navigation is unstable and timing may matter.
- **Mirror Hall:** Distorted versions of the Witch appear; reflection and doppelgänger themes challenge the player (e.g., Mirror Witches that mimic the last spell).

### Strategic Gameplay Loop

1. **Explore carefully** — optionally with limited visibility to increase tension.
2. **Encounter** hostile or corrupted characters (and sometimes environmental hazards).
3. **Decide:** **Freeze** (control), **Heal** (restore), or **Avoid** (risk/reward).
4. **Manage energy** — spend on powers vs. seek regen (crystals, safe zones, movement sacrifice).
5. **Reach the core chamber** — the primary win goal.

**Tension:** Healing enemies may turn them into allies later. Freezing too often may increase corruption in the maze or in the Witch. Overhealing may weaken the Witch (e.g., drain her own vitality). These trade-offs make each encounter a meaningful strategic and moral choice.

### Enemy Types

- **Corrupted Knights:** Aggressive melee attackers; the Witch must Freeze to bypass or create openings, or avoid.
- **Lost Children:** Fast but fragile. Healing them can redeem them and **reveal hidden paths** — a direct payoff for choosing compassion.
- **Mirror Witches:** Mimic your last spell; the player must think tactically about spell order and when to use Freeze vs. Heal.
- **The Labyrinth Itself:** The environment fights back through traps, moving walls, and spreading corruption, so the "enemy" is sometimes the maze.

### Tone & Theme

The experience leans into:

- **Power vs. restraint** — having magic but choosing when (and how) to use it.
- **Mercy vs. control** — Freeze as control, Heal as mercy; neither is purely good or bad.
- **Strength through compassion** — healing and redemption can unlock paths and allies.
- **Emotional discipline** — managing limited resources and moral choices under pressure.

---

## Section B: The Test Strategy (QA & Algorithms)

We practice **Test Driven Development (TDD)**. The following scenarios describe how we will verify the system works: one happy path, one edge case, one failure state, and the solvability check. No code is written here — only the logic and behavior to test.

### The Happy Path

A standard successful interaction:

- The Witch has **sufficient energy** (at least the medium cost for Freeze).
- The player targets a **trap** and uses **Freeze**.
- The system deducts the medium energy cost from the Witch's pool.
- The trap is **disabled** (state updated so it no longer harms or blocks).
- The Witch can **move through the cell safely**.

*Optional second example:* The Witch enters a **safe zone** → the Model applies slow energy regeneration → the Witch's energy pool increases over time (or by a defined amount) while she remains in the zone.

### The Edge Case

A boundary condition:

- The player attempts to use **Freeze** or **Heal** with **insufficient energy** (current energy is less than the cost of the chosen power).
- The system **rejects the action**: no energy is deducted, no target state changes (trap stays active, enemy unchanged).
- The player receives clear feedback (e.g., "Not enough energy" or equivalent).
- The Witch's position (x, y) and all other game state remain unchanged.

*Alternative edge case:* The player attempts to move into a wall or blocked cell → the system rejects the move → position (x, y) unchanged, no energy change.

### The Failure State

Error handling:

- The **save file is missing or corrupted** (e.g., invalid format, truncated data).
- The game **catches the exception** during load (try/catch or equivalent).
- Instead of crashing, the game **loads a default new game** (or returns to main menu with an option to start new game).
- Optionally: log the error or show a short message to the player (e.g., "Save file could not be loaded. Starting new game.").

### The Solvability Check (Algorithm Selection)

**Problem:** A randomly generated labyrinth might have the exit unreachable from the start — e.g., blocked by impassable terrain or disconnected regions. Additionally, **time-based corruption** spreads during gameplay and can block or alter paths; a layout verified as solvable at generation could become **unwinnable** if corruption seals the only route to the exit.

**Solution:** We will use **DFS (Depth-First Search)** to traverse the labyrinth graph. Solvability must be verified in a way that **accounts for time-based corruption**, using one of the following approaches:

- **Approach A — Verify under corruption:** After generating the layout, simulate the **maximum intended corruption spread** (e.g., run the corruption rules forward to a worst-case or time limit). Build the passability graph from the **resulting layout** (cells blocked by corruption are impassable). **The start cell must remain passable after corruption** — either by design (corruption never affects the start cell) or by an explicit check: if the start cell is blocked in the post-corruption layout, reject the layout and regenerate. Then run DFS from the start cell on this graph. Only accept the layout if the exit is still reachable. **For this guarantee to hold during gameplay, runtime corruption must be bounded so it never exceeds this simulated maximum** — e.g., use the same spread rules and a hard cap (time limit or max corrupted cells) so that in-play corruption can never block more of the maze than was simulated. Otherwise, corruption that spreads beyond the simulated worst case during play could still make the maze unwinnable despite passing the generation-time check.
- **Approach B — Design constraint:** Constrain the **corruption mechanic** so that it **never fully seals all paths** to the exit (e.g., by design, at least one path is always left open, or corruption only adds difficulty without ever blocking the sole route). Then the initial-layout DFS check is sufficient, because the mechanic cannot make the maze unwinnable.

Implementation will choose one approach and document it; the important point is that **solvability is not verified only at t = 0** — we must either verify under a corruption model or guarantee by design that the exit stays reachable.

**Logic (no code):**

- Treat the labyrinth as a **graph**: each cell is a node; edges exist between adjacent cells that are passable (no wall, or frozen bridge where applicable). When using Approach A, define passable cells **after** applying the simulated corruption (blocked cells have no edges).
- **Start-cell check (Approach A):** If using Approach A, verify the start cell (e.g., (0, 0)) is still passable in the post-corruption layout. If it is blocked, reject the layout and regenerate — otherwise DFS would have no valid starting point and the check would be invalid.
- Start at the **start cell** (e.g., (0, 0)).
- Run **DFS** from the start, marking every reachable cell.
- After the traversal, check whether the **exit cell** is in the set of reachable cells.
- If **yes**, the labyrinth is solvable for that layout (initial and/or post-corruption); accept the layout for play.
- If **no**, discard and **regenerate** (or fix the layout).

**Why DFS fits:** DFS visits every node in the same connected component as the start. We only need a connectivity check ("can we reach the exit?"). DFS is simple and sufficient for this; the same logic applies whether the graph is the initial layout or the post-corruption layout.

---

## Section C: The Architecture Map (Patterns)

Based on the lecture, we map the game to the **MVC pattern** and note other patterns that fit the design.

### MVC Mapping

- **Model:** Holds all game state and rules. It includes: the **labyrinth** (cells, walls — including moving/shifting where applicable — traps, water, safe zones, light crystals, exit, time-based corruption); **zones/areas** (e.g., Ice Caverns, Ruined Temple, Living Maze, Mirror Hall); the **White Witch** (position, health, energy pool); **powers** (Freeze, Heal) and their costs and effects; **enemy types** (Corrupted Knights, Lost Children, Mirror Witches, environmental hazards) and their states (active, frozen, calm, allied); and **win/loss state**. The Model does not handle user input or rendering; it only updates state when the Controller requests changes and validates those requests.

- **View:** Presents the game to the player. It displays: the current cell/room description, available moves and actions (move, Freeze, Heal), energy and health, and messages (e.g., "Not enough energy," "Trap frozen"). The View can be CLI or GUI; it reads from the Model (or receives updated state from the Controller) and refreshes the display.

- **Controller:** Receives **user input** (move direction, use Freeze, use Heal, target selection). It calls the Model to **validate** and to **update state**. After the Model updates, the Controller triggers the View to **refresh**. The Controller orchestrates flow (e.g., "use Freeze on trap" → Model applies cost and effect → Controller notifies View to update).

### Other Patterns

- **State (or simple state machine):** Distinct states: e.g., **exploring**, **using power / target selection**, **in safe zone** (regen), **game won**, **game lost**, **main menu**. The Controller or a state manager switches between these so input and Model updates match the current phase.

- **Resource / energy system:** The Model exposes the Witch's energy as a resource. The Controller checks energy before applying a power. The Model applies energy changes from: power use (deduct), light crystals (add), safe zones (add over time), sacrifice of movement, and moral decisions. This keeps resource logic in one place and testable.


##Summary of AI Review (ChatGPT Plus)

###Section A: In order to satisfy trivia requirement we may want to add a note that certain doors, guardians, or corruption nodes require answering trivia questions retrieved from the SQLite database to proceed. 

###Section B: BFS could also be used, but since we only need a connectivity check (not shortest path), DFS is sufficient and slightly simpler to implement recursively or with a stack.

###Section C: Database Integration 
Database Layer (within Model or as Repository class):
SQLite database stores:
Trivia questions, Answers, Categories, Difficulty
The Model queries the database when a trivia encounter occurs.
The Controller does not directly access SQLite.
Save/Load functionality serializes game state separately from the trivia database.
That clarifies separation of concerns:
Database = persistent trivia storage
Save file = current game state

