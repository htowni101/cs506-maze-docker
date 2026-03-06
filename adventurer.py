import random

class Adventurer():
    """Represents the player in the game with isometric movement support."""

    def __init__(self, name, start_x=0, start_y=0):
        self.__name = name
        self.__hit_points = random.randint(75, 100)
        self.__max_hit_points = 100
        
        self.__healing_potions = 0
        self.__vision_potions = 0
        self.__pillars_found = []
        
        self.__x = start_x
        self.__y = start_y
        # Current sprite direction: 'ne', 'nw', 'se', 'sw' (updated on movement)
        self.__sprite_direction = 'sw'

    @property
    def hit_points(self):
        """Getter to prevent accidental changes."""
        return self.__hit_points
    
    @property
    def healing_potions(self):
        """Getter to prevent accidental changes."""
        return self.__healing_potions
    
    @property
    def vision_potions(self):
        """Getter to prevent accidental changes."""
        return self.__vision_potions
    
    @property
    def pillars_found(self):
        """Getter for pillars collected."""
        return self.__pillars_found

    def get_location(self):
        """Gets Adventurer's coordinates. Returns a tuple (x, y)."""
        return (self.__x, self.__y)
    
    def get_sprite_direction(self):
        """Returns current sprite direction: 'ne', 'nw', 'se', 'sw'."""
        return self.__sprite_direction

    # Movement handled directly by game.py via coordinate manipulation
            
    def heal(self):
        """Uses Potion to heal and restore Hit Points."""
        if self.__healing_potions > 0:
            # Randomly-generate the healing amount, and add to Hit Points.
            heal_amount = random.randint(5, 15)
            self.__hit_points += heal_amount
            # Ensure hit points total isn't more than the maximum allowed.
            if self.__hit_points > self.__max_hit_points:
                self.__hit_points = self.__max_hit_points
            
            # Subtract Healing Potion after it's been applied to Hit Points total.
            self.__healing_potions -= 1
            return f"Used Potion. Healed {heal_amount} Hit Points."
        else:
            return "You have no Healing Potions."

    def suffer_damage(self, amount):
        """Takes damage. Deduct from Adventurer's Hit Points total."""
        self.__hit_points -= amount
        # If Hit Points is <= 0:
        if self.__hit_points <= 0:
            self.__hit_points = 0
            # Then Adventurer is dead.
            return True
        # Otherwise, Adventurer is still alive.
        return False

    def pick_up_healing_potion(self, room):
        """Picks up the Healing Potion and adds to Adventurer's Healing Point total. """
        room.remove_healing_potion()
        self.__healing_potions += 1

    def pick_up_vision_potion(self, room):
        """Picks up the Vision Potion and increments count."""
        room.remove_vision_potion()
        self.__vision_potions += 1

    def pick_up_pillar(self, room):
        # Take the Pillar in current room, if applicable.
        pillar = room.has_a_pillar()
        if pillar:
            self.__pillars_found.append(pillar)
            room.remove_pillar()

    def __str__(self):
        """Build a string containing Name, Hit Points, Healing Potions, Vision Potions, and Pillars."""
        return (
            f"\n--- Adventurer: {self.__name} ---\n"
            f"HP: {self.__hit_points}/{self.__max_hit_points}\n"
            f"Healing Potions: {self.__healing_potions}\n"
            f"Vision Potions: {self.__vision_potions}\n"
            f"Pillars Found: {', '.join(self.__pillars_found) if self.__pillars_found else 'None'}\n"
        )
