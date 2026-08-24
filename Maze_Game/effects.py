"""
Everything about traps/powerups that ISN'T rendering: the data table
describing each effect, where they get randomly placed in the maze,
and an EffectManager class that tracks which are still active and what
happens when the player triggers one.

Splitting this out from main.py's old apply_effect()/reset_game()
closures into a class is what makes this file possible to have at
all - a pile of `nonlocal` variables can't be imported into another
module and used sensibly, but a class with attributes and methods can.
"""

import math
import random

import config
import maze
import audio

# ---------------------------------------------------------
# TRAPS / POWERUPS - a data-driven effects table
# ---------------------------------------------------------
#   kind:        "trap" or "powerup" (currently just informational)
#   name:        short title shown in the HUD message
#   message:     the explanation shown to the player
#   effect:      which effect this triggers (see EffectManager._apply)
#   duration:    how long the effect lasts, in seconds
#   multiplier:  (speed effects only) movement speed multiplier
#   sound:       filename played once, the moment this effect triggers
#   fixed_count: places EXACTLY this many instances instead of the
#                usual random MIN_EFFECT_COUNT..MAX_EFFECT_COUNT range
EFFECT_TEMPLATES = [
    {
        "kind": "trap",
        "name": "Ice Trap!",
        "message": "You're frozen and can't move for 5 seconds.",
        "effect": "freeze",
        "duration": 5.0,
        "sound": "ice_trap.wav",
    },
    {
        "kind": "trap",
        "name": "Sandpit!",
        "message": "You're slowed down for 10 seconds.",
        # Reuses the same "speed" effect as the boost below - a
        # multiplier under 1.0 slows the player instead of speeding
        # them up. No new movement code needed for this trap at all.
        "effect": "speed",
        "duration": 10.0,
        "multiplier": 0.4,
        "sound": "sandpit_trap.wav",
    },
    {
        "kind": "trap",
        "name": "Teleport Trap!",
        "message": "You've been teleported to a random part of the maze!",
        "effect": "teleport",
        # Unlike other traps, this one is deliberately NOT hidden - it's
        # marked always_visible so the player can see and avoid it if
        # they want, instead of it being a pure surprise.
        "always_visible": True,
        "reveal_color": (0.6, 0.2, 0.9),  # purple
        "sound": "teleport_trap.wav",
    },
    {
        "kind": "powerup",
        "name": "Stamina Refill!",
        "message": "Stamina refilled! Hold SHIFT to sprint.",
        "effect": "stamina",
        "icon": "boot.png",
        "glow_color": (1.0, 0.85, 0.3),  # warm gold
        "sound": "pickup_sound.wav",
    },
    {
        "kind": "powerup",
        "name": "Jump Boost!",
        "message": "Press SPACE to jump - grants 2 uses, and stacks!",
        "effect": "jump",
        "uses": 2,
        "icon": "jump_icon.png",
        "glow_color": (0.4, 0.9, 1.0),  # cool cyan
        "sound": "pickup_sound.wav",
    },
    {
        "kind": "powerup",
        "name": "Goal Vision!",
        "message": "You can see the goal through walls for 30 seconds!",
        "effect": "reveal_goal",
        "duration": 30.0,
        "icon": "eye_icon.png",
        "glow_color": (0.3, 1.0, 0.4),  # matches the beacon's green glow
        "sound": "pickup_sound.wav",
    },
    {
        "kind": "powerup",
        "name": "Path Reveal!",
        "message": "The path to the goal is highlighted for 30 seconds!",
        "effect": "path_reveal",
        "duration": 30.0,
        "icon": "map_icon.png",
        "glow_color": (0.7, 0.4, 1.0),  # violet
        "sound": "pickup_sound.wav",
    },
    {
        "kind": "powerup",
        "name": "Magic Mushroom!",
        "message": "Whoa... reality is melting for 20 seconds!",
        "effect": "mushroom",
        "duration": 20.0,
        "icon": "mushroom_icon.png",
        "glow_color": (1.0, 0.2, 0.8),  # hot pink
        "sound": "pickup_sound.wav",
    },
]


def place_effects():
    """
    Randomly scatters effects across open cells, guaranteeing between
    MIN_EFFECT_COUNT and MAX_EFFECT_COUNT copies of EVERY template -
    not just a fixed total split randomly, which could easily leave
    some effect types over-represented and others missing entirely.
    """
    excluded = {(maze.START_ROW, maze.START_COL), (maze.GOAL_ROW, maze.GOAL_COL)}
    candidates = [
        pos for pos, distance in maze.DISTANCES_FROM_START.items()
        if distance > 4 and pos not in excluded
    ]
    random.shuffle(candidates)  # so pulling positions in order = pulling them randomly
    position_iter = iter(candidates)

    effects = {}
    for template in EFFECT_TEMPLATES:
        if "fixed_count" in template:
            count = template["fixed_count"]
        else:
            count = random.randint(config.MIN_EFFECT_COUNT, config.MAX_EFFECT_COUNT)
        for _ in range(count):
            position = next(position_iter, None)
            if position is None:
                break  # ran out of valid cells - maze too small for this many effects
            effects[position] = dict(template)  # copy - each tile gets its own dict
    return effects


# Generated once at import time - the same layout persists for the
# whole run (restarting via 'R' restores THESE positions, it doesn't
# reshuffle them).
EFFECTS = place_effects()


class EffectManager:
    """
    Tracks which traps/powerups are still un-triggered, any temporary
    movement effect currently in progress (frozen / sped up / slowed),
    and the HUD message queued up to explain the most recent trigger.
    """

    def __init__(self):
        self.active_effects = dict(EFFECTS)
        self.frozen_until = 0.0
        self.frozen_tile_position = None  # (row, col) tinted blue while frozen
        self.speed_multiplier = 1.0
        self.speed_boost_until = 0.0
        self.reveal_goal_until = 0.0  # time.time() value until which the goal beacon shows
        self.path_reveal_until = 0.0  # time.time() value until which the path highlight shows
        self.revealed_path = []       # list of (row, col) cells forming the highlighted route
        self.mushroom_until = 0.0     # time.time() value until which the psychedelic effect shows
        self.stamina = config.STAMINA_MAX_SECONDS  # seconds of sprinting available - starts FULL
        self.teleport_flash_until = 0.0  # time.time() value the portal flash fades out by
        self.current_message = None  # (name, message) tuple, or None
        self.message_until = 0.0

    def reset(self):
        self.__init__()
        # No special music handling needed here: main.py calls
        # audio.update_background_music(is_mushroom_active(now), ...)
        # every frame regardless, and immediately after this reset
        # is_mushroom_active() will correctly be False - the very next
        # frame naturally switches back if the mushroom track had been
        # playing, with no bespoke tracking required in this class.

    def is_frozen(self, now):
        return now < self.frozen_until

    def is_goal_revealed(self, now):
        return now < self.reveal_goal_until

    def is_path_revealed(self, now):
        return now < self.path_reveal_until

    def teleport_flash_alpha(self, now):
        """
        Returns how opaque the portal flash should be right now: peaks
        at TELEPORT_FLASH_MAX_ALPHA the instant the teleport triggers,
        then fades linearly to 0 over TELEPORT_FLASH_DURATION. Returns
        0.0 once it's fully faded (or if no teleport has happened yet).
        """
        if now >= self.teleport_flash_until:
            return 0.0
        remaining = self.teleport_flash_until - now
        fraction = min(remaining / config.TELEPORT_FLASH_DURATION, 1.0)  # 1.0 right at trigger, fading to 0
        return config.TELEPORT_FLASH_MAX_ALPHA * fraction

    def has_stamina(self):
        return self.stamina > 1e-6  # small epsilon - repeated dt subtraction can leave
                                     # a tiny non-zero residual (e.g. 3.6e-14) instead of
                                     # landing on exactly 0.0, which would otherwise still
                                     # technically pass a plain "> 0.0" check

    def consume_stamina(self, dt):
        """Drains stamina while sprinting - clamped so it never goes negative."""
        self.stamina = max(0.0, self.stamina - dt)

    def is_mushroom_active(self, now):
        return now < self.mushroom_until

    def update_expiry(self, now):
        """Call once per frame: clears an expired speed boost/slow."""
        if now >= self.speed_boost_until:
            self.speed_multiplier = 1.0

    def check_tile(self, position, now, player):
        """
        Triggers whatever's at `position`, if anything, consuming it
        (one-time trigger). `player` is passed through so the "jump"
        effect can flip the player's ability flag directly.
        """
        if position not in self.active_effects:
            return
        effect = self.active_effects.pop(position)
        self._apply(effect, position, now, player)

    def apply_fright(self, now, duration, title, message):
        """
        Freezes the player and queues a message, same as the ice trap
        - but callable directly, for things that aren't triggered by
        stepping on a maze tile (the monster catching the player).
        """
        self.frozen_until = now + duration
        self.frozen_tile_position = None  # no specific tile to tint - not a trap trigger
        self.current_message = (title, message)
        self.message_until = now + duration

    def _apply(self, effect, position, now, player):
        if effect["effect"] == "freeze":
            self.frozen_until = now + effect["duration"]
            self.frozen_tile_position = position
            message_seconds = effect["duration"]
            message_text = effect["message"]
        elif effect["effect"] == "speed":
            # STACKS: if a speed effect is already running, extend from
            # its current expiry instead of overwriting it, so back-to-
            # back pickups add up instead of just resetting the clock.
            base_time = max(now, self.speed_boost_until)
            self.speed_boost_until = base_time + effect["duration"]
            self.speed_multiplier = effect["multiplier"]
            message_seconds = 3.0
            message_text = effect["message"]
        elif effect["effect"] == "jump":
            # STACKS: each pickup ADDS charges rather than just setting
            # a single-use flag, so multiple jump powerups accumulate.
            player.jump_charges += effect.get("uses", 1)
            message_seconds = 3.0
            message_text = f"You have {player.jump_charges} jump(s) available - press SPACE!"
        elif effect["effect"] == "reveal_goal":
            # STACKS: same "extend from current expiry" idea as speed.
            base_time = max(now, self.reveal_goal_until)
            self.reveal_goal_until = base_time + effect["duration"]
            message_seconds = effect["duration"]
            message_text = effect["message"]
        elif effect["effect"] == "path_reveal":
            # Recomputes the route from WHEREVER the player currently
            # is (that's `position`, the tile they just triggered this
            # on) to the goal - a fresh path each time, in case this
            # stacks with a pickup from a different location than the
            # first one.
            self.revealed_path = maze.bfs_path(
                maze.MAZE, position, (maze.GOAL_ROW, maze.GOAL_COL)
            )
            base_time = max(now, self.path_reveal_until)
            self.path_reveal_until = base_time + effect["duration"]
            message_seconds = effect["duration"]
            message_text = effect["message"]
        elif effect["effect"] == "mushroom":
            # STACKS the duration same as the other timed powerups.
            # Music switching is NOT handled here - main.py calls
            # audio.update_background_music(is_mushroom_active(now), ...)
            # every frame, which picks up this state change (and its
            # eventual expiry) automatically without this class needing
            # to talk to the audio module about music at all.
            base_time = max(now, self.mushroom_until)
            self.mushroom_until = base_time + effect["duration"]
            message_seconds = effect["duration"]
            message_text = effect["message"]
        elif effect["effect"] == "teleport":
            # Teleports somewhere else in the maze - anywhere except
            # where the player already is or the goal itself
            # (teleporting straight onto the goal would let a "trap"
            # win the game).
            new_row, new_col = maze.random_open_cell(
                exclude={position, (maze.GOAL_ROW, maze.GOAL_COL)}
            )
            player.x = (new_col + 0.5) * config.CELL_SIZE
            player.z = (new_row + 0.5) * config.CELL_SIZE
            self.teleport_flash_until = now + config.TELEPORT_FLASH_DURATION
            message_seconds = 3.0
            message_text = effect["message"]
        elif effect["effect"] == "stamina":
            # A refill, not a stacking timed effect - stamina has a
            # hard cap (STAMINA_MAX_SECONDS), so there's no meaningful
            # "stack beyond the max" the way the timed powerups do.
            self.stamina = config.STAMINA_MAX_SECONDS
            message_seconds = 3.0
            message_text = effect["message"]
        else:
            message_seconds = 3.0
            message_text = effect["message"]

        sound_file = effect.get("sound")
        if sound_file:
            audio.play_effect_sound(sound_file)

        self.current_message = (effect["name"], message_text)
        self.message_until = now + message_seconds