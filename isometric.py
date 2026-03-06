import pygame

# Initialize Pygame
pygame.init()

# Screen dimensions
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 900
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Isometric Grid")

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (100, 100, 100)

# Tile dimensions in isometric view
TILE_WIDTH = 64  # Width of the diamond shape
TILE_HEIGHT = 32 # Height of the diamond shape (half of TILE_WIDTH for 2:1 ratio)

# Grid dimensions
GRID_ROWS = 20
GRID_COLS = 20

# Offset for centering the grid (adjust as needed)
OFFSET_X = SCREEN_WIDTH // 2
OFFSET_Y = SCREEN_HEIGHT // 4 # Start higher up for better visibility

def cartesian_to_isometric(x, y):
    """Converts Cartesian coordinates to isometric screen coordinates."""
    iso_x = (x - y) * (TILE_WIDTH // 2)
    iso_y = (x + y) * (TILE_HEIGHT // 2)
    return iso_x + OFFSET_X, iso_y + OFFSET_Y

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill(BLACK)

    # Draw the isometric grid
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            # Calculate the four corner points of the isometric tile
            # (based on the top-left corner of the "diamond" in isometric space)
            p1_x, p1_y = cartesian_to_isometric(col, row)
            p2_x, p2_y = cartesian_to_isometric(col + 1, row)
            p3_x, p3_y = cartesian_to_isometric(col + 1, row + 1)
            p4_x, p4_y = cartesian_to_isometric(col, row + 1)

            # Draw the lines forming the diamond shape
            pygame.draw.line(screen, GRAY, (p1_x, p1_y), (p2_x, p2_y), 1)
            pygame.draw.line(screen, GRAY, (p2_x, p2_y), (p3_x, p3_y), 1)
            pygame.draw.line(screen, GRAY, (p3_x, p3_y), (p4_x, p4_y), 1)
            pygame.draw.line(screen, GRAY, (p4_x, p4_y), (p1_x, p1_y), 1)

    pygame.display.flip()

pygame.quit()