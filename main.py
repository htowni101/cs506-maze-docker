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



def run_start_menu(screen, repo, player):
    """
    Returns one of:
      ("new", None)
      ("continue", game_record)
      ("load", game_record)
      ("quit", None)
    """
    font_title = pygame.font.Font(None, 72)
    font_btn = pygame.font.Font(None, 44)
    font_sm = pygame.font.Font(None, 28)
    font_xs = pygame.font.Font(None, 22)

    clock = pygame.time.Clock()

    mode = "main"  # "main" or "load"
    selected_game = None
    message = ""

    # Basic button rectangles
    w, h = screen.get_size()
    cx = w // 2

    btn_w, btn_h = 360, 60
    btn_gap = 18
    top_y = h // 2 - 120

    def make_btn(y):
        return pygame.Rect(cx - btn_w // 2, y, btn_w, btn_h)

    btn_new = make_btn(top_y + 0 * (btn_h + btn_gap))
    btn_continue = make_btn(top_y + 1 * (btn_h + btn_gap))
    btn_load = make_btn(top_y + 2 * (btn_h + btn_gap))
    btn_quit = make_btn(top_y + 3 * (btn_h + btn_gap))

    # Load list layout
    list_left = 80
    list_top = 160
    list_row_h = 52
    list_w = w - 160

    def draw_button(rect, label):
        mouse = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse)
        color = (70, 70, 90) if not hover else (100, 100, 140)
        pygame.draw.rect(screen, color, rect, border_radius=10)
        pygame.draw.rect(screen, (200, 200, 230), rect, 2, border_radius=10)
        text = font_btn.render(label, True, (255, 255, 255))
        screen.blit(text, text.get_rect(center=rect.center))

    def draw_title(text):
        t = font_title.render(text, True, (255, 215, 0))
        screen.blit(t, t.get_rect(center=(cx, 80)))

    def refresh_saves():
        # Use your new repo method; default should show in-progress saves
        return repo.list_games_for_player(player.id, limit=10)

    saves_cache = refresh_saves()

    running = True
    while running:
        clock.tick(60)
        screen.fill((10, 10, 18))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ("quit", None)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if mode == "load":
                        mode = "main"
                        message = ""
                    else:
                        return ("quit", None)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos

                if mode == "main":
                    if btn_new.collidepoint((mx, my)):
                        return ("new", None)

                    if btn_continue.collidepoint((mx, my)):
                        latest = repo.get_latest_game_for_player(player.id)
                        if latest is None:
                            message = "No saves found to continue."
                        else:
                            return ("continue", latest)

                    if btn_load.collidepoint((mx, my)):
                        saves_cache = refresh_saves()
                        if not saves_cache:
                            message = "No saves found."
                        else:
                            mode = "load"
                            message = ""

                    if btn_quit.collidepoint((mx, my)):
                        return ("quit", None)

                elif mode == "load":
                    # Click a save row
                    for i, g in enumerate(saves_cache):
                        row_rect = pygame.Rect(list_left, list_top + i * list_row_h, list_w, list_row_h - 6)
                        if row_rect.collidepoint((mx, my)):
                            return ("load", g)

        # ---- Draw UI ----
        if mode == "main":
            draw_title("White Witch's Labyrinth")

            draw_button(btn_new, "New Game")
            draw_button(btn_continue, "Continue")
            draw_button(btn_load, "Load Game")
            draw_button(btn_quit, "Quit")

            if message:
                msg = font_sm.render(message, True, (255, 180, 180))
                screen.blit(msg, msg.get_rect(center=(cx, h - 60)))

            hint = font_sm.render("ESC: Quit", True, (180, 180, 200))
            screen.blit(hint, (20, h - 40))

            dbg_hint = font_xs.render(
                "Debug controls in game: F3 profiler on/off, F4 print summary, F5 restart 60s capture",
                True,
                (140, 140, 165),
            )
            screen.blit(dbg_hint, (20, h - 64))

        else:
            draw_title("Load Game")

            info = font_sm.render("Click a save to load it. ESC to go back.", True, (200, 200, 220))
            screen.blit(info, (list_left, 120))

            if not saves_cache:
                none = font_sm.render("No saves found.", True, (255, 180, 180))
                screen.blit(none, (list_left, list_top))
            else:
                for i, g in enumerate(saves_cache):
                    row_rect = pygame.Rect(list_left, list_top + i * list_row_h, list_w, list_row_h - 6)
                    mouse = pygame.mouse.get_pos()
                    hover = row_rect.collidepoint(mouse)
                    pygame.draw.rect(screen, (40, 40, 60) if not hover else (70, 70, 100), row_rect, border_radius=8)
                    pygame.draw.rect(screen, (170, 170, 210), row_rect, 1, border_radius=8)

                    # Show id + updated + a tiny summary from state if available
                    seed = moves = hp = will = heal = vis = wp = None
                    status = None
                    try:
                        st = g.state or {}
                        seed = st.get("seed")
                        moves = st.get("move_count")
                        hp = st.get("hp")
                        will = st.get("will")
                        heal = st.get("healing_potions")
                        vis = st.get("vision_potions")
                        wp = st.get("will_potions")
                        if st.get("is_complete"):
                            status = "COMPLETE"
                        elif st.get("is_dead"):
                            status = "DEAD"
                        else:
                            status = "IN PROGRESS"
                    except Exception:
                        pass

                    label = f"Save {i+1}  |  id={g.id}  |  updated={g.updated_at}"
                    if seed is not None:
                        label += f"  |  seed={seed}"
                    if moves is not None:
                        label += f"  |  moves={moves}" 
                    if hp is not None and will is not None:
                        label += f"  |  HP={hp}  |  Will={will}"
                    if heal is not None and vis is not None and wp is not None:
                        label += f"  |  Healing Potions={heal}  |  Vision Potions={vis}  |  Will Potions={wp}"
                        label += f"  |  Status={status}"


                    # Compact display so the line fits on screen
                    short_id = str(g.id)[:8]
                    updated = str(g.updated_at).replace("T", " ")[:19]
                    label = f"Save {i+1} | {status} | id={short_id} | {updated}"
                    if seed is not None:
                        label += f" | seed={seed}"
                    if moves is not None:
                        label += f" | moves={moves}"
                    if hp is not None and will is not None:
                        label += f" | HP={hp} Will={will}"

                    # Potions compact    
                    if heal is not None and vis is not None and wp is not None:
                        label += f" | Healing Potions={heal} | Vision Potions={vis} | Will Potions={wp}"

                    
                    def ellipsize(text: str, font: pygame.font.Font, max_width: int) -> str:
                        """Trim text to fit within max_width, adding '...' if needed."""
                        if font.size(text)[0] <= max_width:
                            return text
                        ell = "..."
                        while text and font.size(text + ell)[0] > max_width:
                            text = text[:-1]
                        return text + ell

                    max_text_width = row_rect.width - 24   
                    label = ellipsize(label, font_sm, max_text_width)
                    
                    txt = font_sm.render(label, True, (240, 240, 255))
                    screen.blit(txt, (row_rect.x + 12, row_rect.y + 14))

        pygame.display.flip()

    return ("quit", None)

def main():
    """Launch the White Witch's Labyrinth."""
    settings = load_local_settings()

    # Database
    repo = open_repo("game.db")

    # Prompt for player name (terminal is fine)
    try:
        name = input("Enter your name (or press Enter for 'Hero'): ").strip()
    except (EOFError, KeyboardInterrupt):
        name = ""
    if not name:
        name = "Hero"

    player = repo.get_or_create_player(name)
    print(f"Welcome, {player.handle}!")

    # ---- Start Menu (Pygame) ----
    pygame.init()
    pygame.mixer.init()

    screen = pygame.display.set_mode((1200, 800))
    pygame.display.set_caption("The White Witch's Labyrinth")

    action, rec = run_start_menu(screen, repo, player)
    if action == "quit":
        pygame.quit()
        return

    # Decide which game record to use
    if action == "new":
        seed = random.randint(0, 999_999)

        # Build maze so we have maze_id/version for DB record
        maze = build_dungeon_maze(
            seed=seed,
            width=settings.dungeon_width,
            height=settings.dungeon_height,
            max_rooms=settings.dungeon_max_rooms,
            min_room_size=settings.dungeon_min_room_size,
            max_room_size=settings.dungeon_max_room_size,
        )

        game_rec = repo.create_game(
            player_id=player.id,
            maze_id=maze.maze_id,
            maze_version=maze.maze_version,
            initial_state={"seed": seed},
        )

    else:
        # continue/load gives us an existing GameRecord
        game_rec = rec

        seed = game_rec.state.get("seed")
        if seed is None:
            seed = random.randint(0, 999_999)

        maze = build_dungeon_maze(
            seed=seed,
            width=settings.dungeon_width,
            height=settings.dungeon_height,
            max_rooms=settings.dungeon_max_rooms,
            min_room_size=settings.dungeon_min_room_size,
            max_room_size=settings.dungeon_max_room_size,
        )

    print(f"Generating dungeon (seed={seed})...")
    print(f"Maze: {maze.maze_id}, {len(maze.all_cells())} floor cells")

    # Music starts when gameplay starts
    pygame.mixer.music.load("assets/music/eerie_music.wav")
    pygame.mixer.music.set_volume(0.3)
    pygame.mixer.music.play(-1, fade_ms=5000)

    # Launch game with persistence
    game = Game(
        maze=maze,
        seed=seed,
        repo=repo,
        player_name=player.handle,
        game_id=game_rec.id,
        loaded_state=game_rec.state,
    )
    game.run()



if __name__ == "__main__":
    main()
