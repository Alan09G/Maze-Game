"""
Everything that only cares about the maze's GRID DATA: generating it,
finding the goal, and answering collision questions ("is there a wall
here?"). Nothing in this file touches Pygame or OpenGL - it's pure
data and math, which makes it easy to test or reason about on its own.
"""

import math
import random
from collections import deque

import config


def generate_maze(size):
    """
    Procedurally generates a maze using randomized depth-first search
    (the "recursive backtracker" algorithm).

    Cells live at ODD (row, col) positions, spaced 2 apart, with EVEN
    positions between them reserved as walls - that spacing is what
    lets a wall exist as its own distinct grid entry, rather than
    cells being simply open/closed with nothing to knock down between
    them.

    Returns a size x size grid, 1 = wall, 0 = open path. Guaranteed
    fully connected, since the algorithm only ever carves a spanning
    tree.
    """
    grid = [[1] * size for _ in range(size)]  # start completely solid

    def in_bounds(r, c):
        return 0 < r < size - 1 and 0 < c < size - 1

    start_r, start_c = 1, 1
    grid[start_r][start_c] = 0
    visited = {(start_r, start_c)}
    stack = [(start_r, start_c)]

    while stack:
        r, c = stack[-1]
        unvisited_neighbors = []
        for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            nr, nc = r + dr, c + dc
            if in_bounds(nr, nc) and (nr, nc) not in visited:
                unvisited_neighbors.append((nr, nc))

        if unvisited_neighbors:
            nr, nc = random.choice(unvisited_neighbors)
            wall_r, wall_c = (r + nr) // 2, (c + nc) // 2
            grid[wall_r][wall_c] = 0
            grid[nr][nc] = 0
            visited.add((nr, nc))
            stack.append((nr, nc))
        else:
            stack.pop()  # dead end - backtrack

    return grid


def carve_rooms(grid, size, room_count=40, min_size=3, max_size=7):
    """
    Clears random rectangular areas on top of the corridor maze, so
    open "rooms" get mixed in among the narrow winding hallways. Can
    only remove walls, so it can't break connectivity.
    """
    for _ in range(room_count):
        room_w = random.randint(min_size, max_size)
        room_h = random.randint(min_size, max_size)
        top = random.randint(1, size - room_h - 2)
        left = random.randint(1, size - room_w - 2)
        for r in range(top, top + room_h):
            for c in range(left, left + room_w):
                grid[r][c] = 0


def bfs_distances(grid, start):
    """
    Shortest-path distance (in cells) from `start` to every reachable
    open cell. Used to place the goal genuinely far from spawn, and to
    keep effects from spawning right next to the player.
    """
    size = len(grid)
    distances = {start: 0}
    queue = deque([start])
    while queue:
        r, c = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if (0 <= nr < size and 0 <= nc < size
                    and grid[nr][nc] == 0 and (nr, nc) not in distances):
                distances[(nr, nc)] = distances[(r, c)] + 1
                queue.append((nr, nc))
    return distances


# --- Generate the maze once, at import time ---
def bfs_path(grid, start, goal):
    """
    Returns the list of (row, col) cells forming a shortest path from
    start to goal (inclusive of both ends), or an empty list if goal
    isn't reachable. Same breadth-first search as bfs_distances(), but
    tracking WHERE we came from at each cell so we can walk the path
    back afterward, instead of just how far away everything is.
    """
    if start == goal:
        return [start]

    size = len(grid)
    came_from = {start: None}
    queue = deque([start])

    while queue:
        r, c = queue.popleft()
        if (r, c) == goal:
            break
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if (0 <= nr < size and 0 <= nc < size
                    and grid[nr][nc] == 0 and (nr, nc) not in came_from):
                came_from[(nr, nc)] = (r, c)
                queue.append((nr, nc))

    if goal not in came_from:
        return []

    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


def braid_maze(grid, size, extra_connection_chance):
    """
    The base recursive-backtracker maze is a "perfect maze": a
    spanning tree with exactly ONE path between any two cells, and
    zero loops. That guarantees connectivity, but it's also exactly
    why corridors can feel long and strictly one-directional - there's
    never an alternate route or a shortcut, only the one path.

    This "braids" the maze afterward: every WALL that sits directly
    between two cells that are BOTH ALREADY OPEN (so knocking it down
    connects two existing paths rather than carving into solid rock)
    has a chance to be removed too. That creates loops and shortcuts
    without needing to regenerate anything.
    """
    for row in range(1, size - 1):
        for col in range(1, size - 1):
            if grid[row][col] != 1:
                continue  # only consider actual walls

            if row % 2 == 1 and col % 2 == 0:
                # A horizontal connector: sits between (row, col-1) and
                # (row, col+1), which are both real CELLS (odd column).
                if grid[row][col - 1] == 0 and grid[row][col + 1] == 0:
                    if random.random() < extra_connection_chance:
                        grid[row][col] = 0
            elif row % 2 == 0 and col % 2 == 1:
                # A vertical connector: between (row-1, col) and (row+1, col).
                if grid[row - 1][col] == 0 and grid[row + 1][col] == 0:
                    if random.random() < extra_connection_chance:
                        grid[row][col] = 0


MAZE = generate_maze(config.MAZE_SIZE)
carve_rooms(MAZE, config.MAZE_SIZE)
braid_maze(MAZE, config.MAZE_SIZE, config.MAZE_BRAID_CHANCE)

START_ROW, START_COL = 1, 1  # generate_maze() always carves this cell open

DISTANCES_FROM_START = bfs_distances(MAZE, (START_ROW, START_COL))

# The goal is whichever reachable cell is FARTHEST from the start, by
# corridor distance - not a random pick, which could land close by.
GOAL_ROW, GOAL_COL = max(DISTANCES_FROM_START, key=DISTANCES_FROM_START.get)


# ---------------------------------------------------------
# COLLISION
# ---------------------------------------------------------
def world_to_cell(world_x, world_z):
    col = math.floor(world_x / config.CELL_SIZE)
    row = math.floor(world_z / config.CELL_SIZE)
    return row, col


def is_wall_at(world_x, world_z):
    row, col = world_to_cell(world_x, world_z)
    if row < 0 or row >= len(MAZE) or col < 0 or col >= len(MAZE[0]):
        return True
    return MAZE[row][col] == 1


def player_collides_at(world_x, world_z):
    r = config.PLAYER_RADIUS
    corners = [
        (world_x - r, world_z - r),
        (world_x + r, world_z - r),
        (world_x - r, world_z + r),
        (world_x + r, world_z + r),
    ]
    return any(is_wall_at(cx, cz) for cx, cz in corners)


def try_move(current_x, current_z, dx, dz):
    new_x, new_z = current_x, current_z
    if not player_collides_at(current_x + dx, current_z):
        new_x = current_x + dx
    if not player_collides_at(new_x, current_z + dz):
        new_z = current_z + dz
    return new_x, new_z


def reached_goal(world_x, world_z):
    row, col = world_to_cell(world_x, world_z)
    return row == GOAL_ROW and col == GOAL_COL


def random_open_cell(exclude=()):
    """
    Returns a random reachable open cell, optionally excluding some
    specific positions (e.g. the player's current cell, or the goal).
    Shared by the teleport trap and the monster's "catch" consequence.
    """
    candidates = [pos for pos in DISTANCES_FROM_START if pos not in exclude]
    return random.choice(candidates)