"""Isometric dungeon generator with procedural rooms and corridors."""
import os
import random
import sys


class Dungeon:
    """Rectangular rooms with coordinates and intersection detection."""
    
    def __init__(self, x, y, width, height):
        self.x1, self.y1 = x, y
        self.x2, self.y2 = x + width - 1, y + height - 1
        self.center_x = (self.x1 + self.x2) // 2
        self.center_y = (self.y1 + self.y2) // 2

    def intersects(self, other):
        """Check if this room intersects another room."""
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and 
                self.y1 <= other.y2 and self.y2 >= other.y1)


def generate_dungeon(width, height, max_rooms, min_room_size, max_room_size, 
                     min_rooms=6, max_attempts=30, rng=None):
    """Generate procedural dungeon with rooms, corridors, and perimeter tiles."""
    if rng is None:
        rng = random
    dungeon = [['#'] * width for _ in range(height)]
    tile_types = [[None] * width for _ in range(height)]
    room_mask = [[False] * width for _ in range(height)]
    dead_end_mask = [[False] * width for _ in range(height)]  # Track dead-end tiles
    dead_end_candidates = []  # Collect final tiles of dead-end corridors
    rooms = []

    # ===== PHASE 1: LAYOUT GENERATION =====
    # Generate rooms
    for attempt in range(max_attempts):
        if len(rooms) >= min_rooms:
            break
        for _ in range(max_rooms):
            w, h = rng.randint(min_room_size, max_room_size), rng.randint(min_room_size, max_room_size)
            x, y = rng.randint(1, width - w - 1), rng.randint(1, height - h - 1)
            new_room = Dungeon(x, y, w, h)

            if not any(new_room.intersects(r) for r in rooms):
                rooms.append(new_room)
                for ry in range(new_room.y1, new_room.y2 + 1):
                    for rx in range(new_room.x1, new_room.x2 + 1):
                        dungeon[ry][rx] = '.'
                        room_mask[ry][rx] = True

    # Carve corridors between rooms
    if len(rooms) >= 2:
        clamp = lambda val, lo, hi: max(lo, min(hi, val))
        
        for r1, r2 in zip(rooms[:-1], rooms[1:]):
            horizontal_first = rng.random() < 0.5
            
            if horizontal_first:
                exit_x = r1.x2 + 1 if r2.center_x > r1.center_x else r1.x1 - 1
                exit_y = clamp(r1.center_y, r1.y1, r1.y2)
                target_x = r2.center_x
                for cx in range(min(exit_x, target_x), max(exit_x, target_x) + 1):
                    if 0 <= exit_y < height and 0 <= cx < width and not room_mask[exit_y][cx]:
                        dungeon[exit_y][cx] = '.'
                entry_x = clamp(target_x, r2.x1, r2.x2)
                entry_y = r2.y1 - 1 if exit_y < r2.center_y else r2.y2 + 1
                for cy in range(min(exit_y, entry_y), max(exit_y, entry_y) + 1):
                    if 0 <= cy < height and 0 <= entry_x < width and not room_mask[cy][entry_x]:
                        dungeon[cy][entry_x] = '.'
            else:
                exit_y = r1.y2 + 1 if r2.center_y > r1.center_y else r1.y1 - 1
                exit_x = clamp(r1.center_x, r1.x1, r1.x2)
                target_y = r2.center_y
                for cy in range(min(exit_y, target_y), max(exit_y, target_y) + 1):
                    if 0 <= cy < height and 0 <= exit_x < width and not room_mask[cy][exit_x]:
                        dungeon[cy][exit_x] = '.'
                entry_y = clamp(target_y, r2.y1, r2.y2)
                entry_x = r2.x1 - 1 if exit_x < r2.center_x else r2.x2 + 1
                for cx in range(min(exit_x, entry_x), max(exit_x, entry_x) + 1):
                    if 0 <= entry_y < height and 0 <= cx < width and not room_mask[entry_y][cx]:
                        dungeon[entry_y][cx] = '.'

    # Generate dead-end corridors with turns (maze-like)
    num_dead_ends = rng.randint(3, 8)
    for _ in range(num_dead_ends):
        if not rooms:
            break
        room = rng.choice(rooms)
        
        # Pick random exit direction from room
        direction = rng.choice(['n', 'e', 's', 'w'])
        if direction == 'n':
            start_x = rng.randint(room.x1 + 1, room.x2 - 1)
            start_y = room.y1 - 1
            dx, dy = 0, -1
        elif direction == 's':
            start_x = rng.randint(room.x1 + 1, room.x2 - 1)
            start_y = room.y2 + 1
            dx, dy = 0, 1
        elif direction == 'w':
            start_x = room.x1 - 1
            start_y = rng.randint(room.y1 + 1, room.y2 - 1)
            dx, dy = -1, 0
        else:  # 'e'
            start_x = room.x2 + 1
            start_y = rng.randint(room.y1 + 1, room.y2 - 1)
            dx, dy = 1, 0
        
        # Carve corridor with random turns, tracking the final position
        x, y = start_x, start_y
        num_turns = rng.randint(7, 8)
        turns_made = 0
        segment_length = rng.randint(7, 8)
        steps = 0
        corridor_tiles = []
        
        for _ in range(50):  # Max total steps to prevent infinite loop
            if not (0 <= x < width and 0 <= y < height):
                break
            if dungeon[y][x] == '.' or room_mask[y][x]:
                break
            
            dungeon[y][x] = '.'
            corridor_tiles.append((y, x))
            steps += 1
            
            # Check if we should turn
            if steps >= segment_length and turns_made < num_turns:
                # Pick perpendicular direction
                if dx == 0:  # Currently moving vertically
                    dx, dy = rng.choice([(-1, 0), (1, 0)])
                else:  # Currently moving horizontally
                    dx, dy = rng.choice([(0, -1), (0, 1)])
                turns_made += 1
                segment_length = rng.randint(3, 8)
                steps = 0
            
            x += dx
            y += dy
        
        # Store the final tile for later marking
        if corridor_tiles:
            dead_end_candidates.append(corridor_tiles[-1])

    # Mark true dead-ends: tiles with exactly 1 cardinal floor neighbor after all carving
    for final_y, final_x in dead_end_candidates:
        if not (0 <= final_y < height and 0 <= final_x < width):
            continue
        connections = 0
        
        if final_y > 0 and dungeon[final_y - 1][final_x] == '.':
            connections += 1
        if final_y < height - 1 and dungeon[final_y + 1][final_x] == '.':
            connections += 1
        if final_x > 0 and dungeon[final_y][final_x - 1] == '.':
            connections += 1
        if final_x < width - 1 and dungeon[final_y][final_x + 1] == '.':
            connections += 1
        
        # Only mark as dead-end if it has exactly 1 connection (true dead-end tip)
        if connections == 1:
            dead_end_mask[final_y][final_x] = True

    # ===== PHASE 2: PERIMETER CALCULATION =====
    # For each floor tile, calculate which sides are open (touching blank spaces)
    # and which are closed (touching other floor tiles or beyond dungeon edge)
    def is_floor(y, x):
        """Check if position is within bounds and is a floor tile."""
        if not (0 <= y < height and 0 <= x < width):
            return False
        return dungeon[y][x] == '.'

    def get_open_sides(y, x):
        """Return which sides are OPEN (facing blank spaces). Returns set of directions."""
        open_sides = set()
        # NE (north): check y-1, x
        if y == 0 or dungeon[y - 1][x] == '#':
            open_sides.add('ne')
        # SW (south): check y+1, x
        if y == height - 1 or dungeon[y + 1][x] == '#':
            open_sides.add('sw')
        # NW (west): check y, x-1
        if x == 0 or dungeon[y][x - 1] == '#':
            open_sides.add('nw')
        # SE (east): check y, x+1
        if x == width - 1 or dungeon[y][x + 1] == '#':
            open_sides.add('se')
        return open_sides

    # ===== PHASE 3: TILE TYPE ASSIGNMENT =====
    # Assign tile types based on open sides
    for y in range(height):
        for x in range(width):
            if dungeon[y][x] != '.':
                continue
            
            open_sides = get_open_sides(y, x)
            closed_sides = {'ne', 'sw', 'nw', 'se'} - open_sides
            
            # DEAD-END TILES: Check dead-end status FIRST
            if dead_end_mask[y][x]:
                # This tile is marked as a dead-end tip
                # Count how many cardinal neighbors are floor tiles (excluding edges)
                floor_neighbors = 0
                if y > 0 and dungeon[y - 1][x] == '.':
                    floor_neighbors += 1
                if y < height - 1 and dungeon[y + 1][x] == '.':
                    floor_neighbors += 1
                if x > 0 and dungeon[y][x - 1] == '.':
                    floor_neighbors += 1
                if x < width - 1 and dungeon[y][x + 1] == '.':
                    floor_neighbors += 1
                
                # Assign a dead-end sprite based on which direction has the single connection
                # or pick the primary direction if 2+ connections
                if y > 0 and dungeon[y - 1][x] == '.' and floor_neighbors == 1:
                    # Only northern neighbor
                    tile_types[y][x] = 'sw_dead'
                elif y < height - 1 and dungeon[y + 1][x] == '.' and floor_neighbors == 1:
                    # Only southern neighbor
                    tile_types[y][x] = 'ne_dead'
                elif x > 0 and dungeon[y][x - 1] == '.' and floor_neighbors == 1:
                    # Only western neighbor
                    tile_types[y][x] = 'se_dead'
                elif x < width - 1 and dungeon[y][x + 1] == '.' and floor_neighbors == 1:
                    # Only eastern neighbor
                    tile_types[y][x] = 'nw_dead'
                else:
                    # Multiple neighbors - pick dominant direction
                    # Prefer north/south over east/west
                    if y > 0 and dungeon[y - 1][x] == '.':
                        tile_types[y][x] = 'sw_dead'
                    elif y < height - 1 and dungeon[y + 1][x] == '.':
                        tile_types[y][x] = 'ne_dead'
                    elif x > 0 and dungeon[y][x - 1] == '.':
                        tile_types[y][x] = 'se_dead'
                    elif x < width - 1 and dungeon[y][x + 1] == '.':
                        tile_types[y][x] = 'nw_dead'
                    else:
                        # Shouldn't happen, but fallback
                        tile_types[y][x] = 'sw_dead'
            
            # CORNER TILES: two adjacent sides closed
            elif closed_sides == {'ne', 'nw'}:
                tile_types[y][x] = 's'  # South corner
            elif closed_sides == {'ne', 'se'}:
                tile_types[y][x] = 'w'  # West corner
            elif closed_sides == {'sw', 'se'}:
                tile_types[y][x] = 'n'  # North corner
            elif closed_sides == {'sw', 'nw'}:
                tile_types[y][x] = 'e'  # East corner
            
            # WALL TILES: one side open (three sides closed)
            elif closed_sides == {'ne', 'nw', 'se'}:
                tile_types[y][x] = 'sw_wall'  # Open to south
            elif closed_sides == {'ne', 'nw', 'sw'}:
                tile_types[y][x] = 'se_wall'  # Open to east
            elif closed_sides == {'ne', 'sw', 'se'}:
                tile_types[y][x] = 'nw_wall'  # Open to west
            elif closed_sides == {'nw', 'sw', 'se'}:
                tile_types[y][x] = 'ne_wall'  # Open to north
            
            # SINGLE-CLOSED WALLS: three sides open (opposite of above)
            # These are often at corridor endpoints or wide-open areas
            elif closed_sides == {'ne'}:
                # Only NE closed, rest open - treat as wall open to ne side
                tile_types[y][x] = 'ne_wall'
            elif closed_sides == {'sw'}:
                # Only SW closed
                tile_types[y][x] = 'sw_wall'
            elif closed_sides == {'nw'}:
                # Only NW closed
                tile_types[y][x] = 'nw_wall'
            elif closed_sides == {'se'}:
                # Only SE closed
                tile_types[y][x] = 'se_wall'
            
            # HALL TILES: opposite sides open (diagonal pattern)
            elif closed_sides == {'ne', 'sw'}:
                # Open to nw and se: horizontal hall
                tile_types[y][x] = 'nw_hall'
            elif closed_sides == {'nw', 'se'}:
                # Open to ne and sw: vertical hall
                tile_types[y][x] = 'ne_hall'
            
            # INTERSECTION: all or mostly open
            else:
                tile_types[y][x] = 'floor'  # Default for intersections or ambiguous cases

    # ===== PHASE 3.5: CLEANUP STRAY WALL-LIKE TILES =====
    # Occasionally a floor tile with only one floor neighbor slips through without being
    # marked as a dead-end. Reclassify those tiles as proper dead-ends (or delete if isolated).
    for y in range(height):
        for x in range(width):
            if dungeon[y][x] != '.':
                continue

            floor_neighbors = []
            if y > 0 and dungeon[y - 1][x] == '.':
                floor_neighbors.append(('n', y - 1, x))
            if y < height - 1 and dungeon[y + 1][x] == '.':
                floor_neighbors.append(('s', y + 1, x))
            if x > 0 and dungeon[y][x - 1] == '.':
                floor_neighbors.append(('w', y, x - 1))
            if x < width - 1 and dungeon[y][x + 1] == '.':
                floor_neighbors.append(('e', y, x + 1))

            if len(floor_neighbors) == 0:
                # Isolated orphan tile: delete it entirely
                dungeon[y][x] = '#'
                tile_types[y][x] = None
            elif len(floor_neighbors) == 1:
                # Single-connection tile: force a matching dead-end sprite
                direction = floor_neighbors[0][0]
                if direction == 'n':
                    tile_types[y][x] = 'sw_dead'
                elif direction == 's':
                    tile_types[y][x] = 'ne_dead'
                elif direction == 'w':
                    tile_types[y][x] = 'se_dead'
                elif direction == 'e':
                    tile_types[y][x] = 'nw_dead'

    return dungeon, tile_types, rooms