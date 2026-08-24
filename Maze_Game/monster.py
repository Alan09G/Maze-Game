"""
A relentlessly pursuing enemy loosely INSPIRED BY "La Llorona" (The
Weeping Woman), a well-known figure in Mexican and broader Latin
American folklore. This is an original, game-specific creature - a
chasing AI enemy with a cry sound cue and a "catch" consequence -
built for this maze, not a depiction of any real person, and not
based on any particular book/film/game adaptation of the tale.
"""

import math
import random

import config
import maze
import audio


class Monster:
    def __init__(self):
        row, col = self._pick_spawn_cell()
        self.row, self.col = row, col
        self.x = (col + 0.5) * config.CELL_SIZE
        self.z = (row + 0.5) * config.CELL_SIZE
        self._start_x, self._start_z = self.x, self.z

        # Grid-to-grid movement, interpolated smoothly between cells
        # rather than teleporting cell-to-cell - move_progress tracks
        # how far through the CURRENT step she is (0.0 to 1.0).
        self.target_row, self.target_col = row, col
        self.target_x, self.target_z = self.x, self.z
        self.move_progress = 1.0  # 1.0 = arrived, ready to choose a new target

        self._path = []
        self._last_path_update = 0.0
        self._last_cry_time = 0.0

    def _pick_spawn_cell(self):
        candidates = [
            pos for pos, distance in maze.DISTANCES_FROM_START.items()
            if distance > config.MONSTER_MIN_SPAWN_DISTANCE
        ]
        if not candidates:  # fallback, in case of an unusually small maze
            candidates = list(maze.DISTANCES_FROM_START.keys())
        return random.choice(candidates)

    def _pick_next_cell(self, player_row, player_col, now):
        """
        Always heads toward the player's current cell via shortest
        path - no more "wander when far, chase when close" branching.

        The path itself is only RECOMPUTED periodically (BFS over the
        whole maze 60 times a second would be wasteful), but it must
        still be CONSUMED one step at a time as she moves - each call
        pops the step she just used off the front, so the next call
        continues along the remaining route instead of repeatedly
        returning the same already-visited step.
        """
        path_out_of_sync = not self._path or self._path[0] != (self.row, self.col)
        stale = now - self._last_path_update > config.MONSTER_PATH_REFRESH_SECONDS

        if path_out_of_sync or stale:
            self._path = maze.bfs_path(maze.MAZE, (self.row, self.col), (player_row, player_col))
            self._last_path_update = now

        if len(self._path) > 1:
            next_cell = self._path[1]
            self._path = self._path[1:]  # consume this step for next time
            return next_cell
        return (self.row, self.col)

    def _current_speed(self, player_x, player_z):
        """
        Speed ramps up smoothly as she gets closer to the player,
        rather than a sudden jump at some fixed distance - from
        MONSTER_MOVE_SPEED at MONSTER_SPEED_RAMP_RADIUS or farther, up
        to MONSTER_MAX_MOVE_SPEED once she's essentially on top of the
        player. Evaluated fresh every frame (not just when she starts
        a new grid step), so the ramp responds continuously even
        mid-movement between cells.
        """
        distance = math.hypot(self.x - player_x, self.z - player_z)
        ramp_radius = config.MONSTER_SPEED_RAMP_RADIUS
        if distance >= ramp_radius:
            return config.MONSTER_MOVE_SPEED

        closeness = 1.0 - (distance / ramp_radius)  # 0 at the ramp's edge, 1 when touching
        speed_range = config.MONSTER_MAX_MOVE_SPEED - config.MONSTER_MOVE_SPEED
        return config.MONSTER_MOVE_SPEED + speed_range * closeness

    def _maybe_cry(self, now, player_x, player_z):
        """
        Plays her cry sound, but only when the player is actually
        close (within MONSTER_CRY_TRIGGER_RADIUS) - not on a fixed
        timer regardless of distance. A minimum gap
        (MONSTER_CRY_MIN_INTERVAL_SECONDS) between cries is enforced
        either way, so being close doesn't cause a rapid-fire buzz of
        sound. More distinct cues (e.g. footsteps, a different sound
        when actively chasing) can slot in here later the same way.
        """
        distance = math.hypot(self.x - player_x, self.z - player_z)
        if distance > config.MONSTER_CRY_TRIGGER_RADIUS:
            return  # too far away for a cue at all right now

        if now - self._last_cry_time < config.MONSTER_CRY_MIN_INTERVAL_SECONDS:
            return  # still within the minimum buffer since the last cry

        self._last_cry_time = now
        audio.play_monster_cry(config.MONSTER_CRY_MAX_VOLUME)

    def update(self, dt, now, player_row, player_col, player_x, player_z):
        speed = self._current_speed(player_x, player_z)  # cells per second, distance-dependent

        # Her TRUE current cell, from her actual continuous position -
        # not self.row/self.col, which only update the instant she
        # arrives at a target and would be stale mid-transit.
        current_row, current_col = maze.world_to_cell(self.x, self.z)

        if (current_row, current_col) == (player_row, player_col):
            # Same cell as the player: grid-based pathing has nothing
            # left to offer here (bfs_path(cell, same cell) is a single
            # cell with no next step), which is exactly what used to
            # cause her to park at the cell's CENTER and never close
            # the final gap if the player wasn't standing precisely
            # there too. Steer directly toward the player's exact
            # position instead - safe from clipping through walls,
            # since a single maze cell is fully open with nothing
            # inside it to clip through.
            dx = player_x - self.x
            dz = player_z - self.z
            distance = math.hypot(dx, dz)
            if distance > 1e-6:
                step = min(speed * config.CELL_SIZE * dt, distance)
                self.x += dx / distance * step
                self.z += dz / distance * step

            # Keep the grid-target bookkeeping in sync with reality, so
            # movement resumes smoothly (no sudden snap) if the player
            # leaves this cell before she catches up.
            self.row, self.col = current_row, current_col
            self.target_row, self.target_col = current_row, current_col
            self.target_x, self.target_z = self.x, self.z
            self.move_progress = 1.0
        else:
            self.move_progress += dt * speed

            if self.move_progress >= 1.0:
                # Arrived - snap exactly to the target, then pick the next one.
                self.row, self.col = self.target_row, self.target_col
                self.x, self.z = self.target_x, self.target_z
                self._start_x, self._start_z = self.x, self.z

                next_row, next_col = self._pick_next_cell(player_row, player_col, now)
                self.target_row, self.target_col = next_row, next_col
                self.target_x = (next_col + 0.5) * config.CELL_SIZE
                self.target_z = (next_row + 0.5) * config.CELL_SIZE
                self.move_progress = 0.0
            else:
                # Still moving between the previous cell and the target -
                # linear interpolation for smooth motion instead of a
                # visible snap every time she enters a new cell.
                t = self.move_progress
                self.x = self._start_x + (self.target_x - self._start_x) * t
                self.z = self._start_z + (self.target_z - self._start_z) * t

        self._maybe_cry(now, player_x, player_z)

    def is_touching_player(self, player_x, player_z):
        return math.hypot(self.x - player_x, self.z - player_z) < config.MONSTER_CATCH_RADIUS

    def reset(self):
        self.__init__()