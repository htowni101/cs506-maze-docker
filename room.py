import random

class Room:
    """Represents a room in the dungeon with items, obstacles, and fog of war."""
    ITEM_PROB = 0.1  # 10% chance for each item
    
    # ASCII to PNG asset mappings
    ASSET_MAP = {
        'pillar_a': 'pillar_b_s.png',      # Blue pillar
        'pillar_e': 'pillar_g_s.png',      # Green pillar
        'pillar_i': 'pillar_p_s.png',      # Purple pillar
        'pillar_p': 'pillar_y_s.png',      # Yellow pillar
        'pit': 'pit.png',
        'healing_potion': 'potion_h_s.png',
        'vision_potion': 'potion_t_s.png',
        'entrance_nw': 'nw_door_o_s.png',
        'entrance_ne': 'ne_door_o_s.png',
        'exit_nw': 'nw_door_c_s.png',
        'exit_ne': 'ne_door_c_s.png',
    }

    def __init__(self, x, y, tile_type='floor'):
        self.x = x
        self.y = y
        self.entrance = False
        self.entrance_asset = None  # 'entrance_nw' or 'entrance_ne'
        self.exit = False
        self.exit_asset = None      # 'exit_nw' or 'exit_ne'
        self.entrance_tile = None
        self.exit_tile = None
        self.pillar = None          # Pillar type if present in this room
        self.pillar_tile = None     # (x, y) tile where pillar is located
        self.pillar = None          # 'pillar_a', 'pillar_e', 'pillar_i', 'pillar_p'
        
        # Tile-specific item locations (stores (x, y) coordinate or None)
        self.potion_tile = None     # (x, y) of healing or vision potion
        self.potion_type = None     # 'healing' or 'vision'
        self.pit_tiles = set()      # Set of (x, y) coordinates with pits
        
        self.fog_of_war = False     # True = fog present, False = visible
    
    def set_potion_location(self, tile_x, tile_y, potion_type='healing'):
        """Set the location of a single potion (healing or vision) in this room."""
        self.potion_tile = (tile_x, tile_y)
        self.potion_type = potion_type
    
    def add_pit_tile(self, tile_x, tile_y):
        """Add a pit to a specific tile in this room."""
        self.pit_tiles.add((tile_x, tile_y))
    
    def has_potion_at(self, tile_x, tile_y):
        """Check if a potion is at a specific tile."""
        return self.potion_tile == (tile_x, tile_y)
    
    def get_potion_type_at(self, tile_x, tile_y):
        """Get potion type at specific tile ('healing', 'vision', or None)."""
        if self.potion_tile == (tile_x, tile_y):
            return self.potion_type
        return None
    
    def has_pit_at(self, tile_x, tile_y):
        """Check if a pit is at a specific tile."""
        return (tile_x, tile_y) in self.pit_tiles
    
    def remove_healing_potion(self):
        """Remove the healing potion from this room."""
        if self.potion_type == 'healing':
            self.potion_tile = None
            self.potion_type = None
    
    def remove_vision_potion(self):
        """Remove the vision potion from this room."""
        if self.potion_type == 'vision':
            self.potion_tile = None
            self.potion_type = None
    
    def has_healing_potion(self):
        """Check if room has a healing potion."""
        return self.potion_type == 'healing'
    
    def has_vision_potion(self):
        """Check if room has a vision potion."""
        return self.potion_type == 'vision'
    
    def has_pit(self):
        """Check if room has any pits."""
        return len(self.pit_tiles) > 0

    def remove_pillar(self):
        self.pillar = None
        self.pillar_tile = None
    
    def clear_fog_of_war(self):
        """Remove fog from this room."""
        self.fog_of_war = False
    
    def has_a_pillar(self):
        return self.pillar is not None
    
    def set_pillar_tile(self, x, y, pillar_type):
        """Set pillar location and type."""
        self.pillar_tile = (x, y)
        self.pillar = pillar_type


