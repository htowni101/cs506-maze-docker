"""
main.py - Game Launcher

Slim launcher that builds a dungeon maze, opens a repository,
and starts the pygame game loop.

CONSTRAINTS:
  - ONLY module allowed to import maze, db, game, and npc_data.
  - Enforces boundaries: maze never talks to db.
"""
from __future__ import annotations

import random
import sys
import pygame

from pathlib import Path

from maze import build_dungeon_maze
from db import open_repo
from game import Game
from local_settings import load_local_settings


def main():
    """Launch the White Witch's Labyrinth."""
    settings = load_local_settings()

    # Seed
    seed = random.randint(0, 999_999)

    # Database
    repo = open_repo("game.db")

    # Prompt for player name
    try:
        name = input("Enter your name (or press Enter for 'Hero'): ").strip()
    except (EOFError, KeyboardInterrupt):
        name = ""
    if not name:
        name = "Hero"

    player = repo.get_or_create_player(name)
    print(f"Welcome, {player.handle}!")

    # Generate maze
    print(f"Generating dungeon (seed={seed})...")
    maze = build_dungeon_maze(
        seed=seed,
        width=settings.dungeon_width,
        height=settings.dungeon_height,
        max_rooms=settings.dungeon_max_rooms,
        min_room_size=settings.dungeon_min_room_size,
        max_room_size=settings.dungeon_max_room_size,
    )
    print(f"Maze: {maze.maze_id}, {len(maze.all_cells())} floor cells")
    # Music plays when the game starts
    pygame.init()
    pygame.mixer.init()
    pygame.mixer.music.load("assets/music/eerie_music.wav")
    pygame.mixer.music.set_volume(0.3)
    pygame.mixer.music.play(-1, fade_ms=5000)

    # Create game record
    game_rec = repo.create_game(
        player_id=player.id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state={"seed": seed},
    )

    # Launch pygame
    game = Game(
        maze=maze,
        seed=seed,
        repo=repo,
        player_name=player.handle,
    )
    game.run()


if __name__ == "__main__":
    main()
