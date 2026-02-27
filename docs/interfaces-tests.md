# Interface Test Plan

## Maze Contract Tests
- Initializes a 3x3 maze
- Returns current position
- Rejects invalid moves
- Accepts valid moves
- Does not print or read input

## Repository Contract Tests
- load() returns None when no save exists
- save() persists JSON-safe data
- load() returns saved state
- Does not import maze

## Engine Integration Tests
- Starts new game if load() returns None
- Loads game if save exists
- Accepts N/S/E/W input
- Saves state after move
- Quits cleanly
