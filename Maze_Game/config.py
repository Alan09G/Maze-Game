"""
All tunable numbers for the game, in one place. If you want to change
how big the maze is, how fast the player moves, how high they jump,
etc. - this is the file to open first.
"""

# --- Display ---
DISPLAY_WIDTH = 900
DISPLAY_HEIGHT = 600

# --- Maze ---
# MAZE_SIZE must be ODD - the generation algorithm relies on a solid
# border plus alternating cell/wall positions. 101 is the nearest odd
# number to a requested 100x100.
MAZE_SIZE = 101
CELL_SIZE = 2.0       # world units per grid cell
WALL_HEIGHT = 2.0
VIEW_RADIUS = 14      # cells around the player actually rendered each frame
MAZE_BRAID_CHANCE = 0.25  # fraction of removable "redundant" walls knocked down for loops/shortcuts

# Facing-direction culling: skips drawing cells well outside the
# camera's forward cone, since roughly HALF of the VIEW_RADIUS window
# sits behind the player at any moment and is never actually on
# screen. CULL_HALF_ANGLE_DEGREES is deliberately generous (the real
# rendering FOV is 70, so its half-angle is 35) - it only needs to
# exclude cells that are unambiguously out of view, with margin to
# spare, not tightly hug the actual FOV.
CULL_HALF_ANGLE_DEGREES = 100
CULL_SKIP_RADIUS_CELLS = 3  # always draw cells this close, regardless of facing direction

# --- Sky / night atmosphere ---
SKY_COLOR = (0.03, 0.04, 0.10)      # deep navy night sky - also doubles as the fog color
SKYBOX_SIZE = 250.0                 # must stay comfortably within the far clip plane (300)
STAR_COUNT = 700
MOONLIGHT_TINT = (0.55, 0.62, 0.82)  # cool, dim tint on walls/floor for a moonlit (not daylit) look

# Fog: fixed-function OpenGL has this built in - no shaders needed.
# Its color matches SKY_COLOR so distant geometry fades smoothly into
# the night sky rather than just vanishing, and its END distance sits
# just past VIEW_RADIUS*CELL_SIZE, softening the abrupt pop-in/out at
# the edge of the maze's view-distance culling window.
FOG_START = 10.0
FOG_END = 34.0

# --- Lighting ---
# A single DIRECTIONAL light ("moonlight") - not a positional or spot
# light attached to the camera. Direction lights have no position, no
# cone, and no distance falloff: every surface is lit purely based on
# the angle between its normal and this fixed direction, everywhere,
# consistently. That sidesteps every problem a camera-attached
# spotlight ran into (nearby geometry falling outside a narrow cone,
# floor not being illuminated by a level-aimed beam, etc.) - this is
# ambiance, not a gameplay mechanic, so simple and robust matters more
# here than a literal beam would.
#
# (x, y, z, 0.0) - the trailing 0.0 is what makes OpenGL treat this as
# a direction rather than a position. Points from high up and slightly
# to the side, like real moonlight.
MOON_LIGHT_DIRECTION = (0.35, 0.85, 0.4, 0.0)

# Split roughly evenly between the constant ambient baseline (light-
# model ambient, applies to every surface regardless of orientation)
# and the directional diffuse contribution (only applies to surfaces
# angled toward the light). A face directly facing the light gets
# roughly ambient+diffuse; a face angled away gets only ambient - so
# there's real shading contrast, but nothing goes pure black.
AMBIENT_LIGHT = (0.5, 0.52, 0.62, 1.0)
MOON_LIGHT_DIFFUSE = (0.5, 0.52, 0.62, 1.0)

# --- Player / movement ---
PLAYER_RADIUS = 0.3
BASE_MOVE_SPEED = 4.0
MOUSE_SENSITIVITY = 0.15

# --- Stamina / sprint ---
STAMINA_MAX_SECONDS = 7.0     # a full tank lasts this many seconds of sprinting - also the hard cap
STAMINA_SPRINT_MULTIPLIER = 2.0  # movement speed while sprinting (multiplies BASE_MOVE_SPEED)
STAMINA_BAR_WIDTH = 200
STAMINA_BAR_HEIGHT = 22
STAMINA_BAR_MARGIN = 20

# --- Jump physics ---
GROUND_Y = 1.0  # normal eye height - where the player rests when not jumping
# Jump height = JUMP_SPEED^2 / (2 * |GRAVITY|) - height scales with the
# SQUARE of speed. This is now the SECOND "3x higher" request in a
# row: the previous value already gave 3x the original height, and
# tripling height again means multiplying speed by another sqrt(3) -
# so overall speed is 5.5 * sqrt(3) * sqrt(3) = 5.5 * 3.
# Resulting peak height ≈ 9.7 world units - GROUND_Y (1.0) + that
# comfortably clears WALL_HEIGHT (2.0), so you'll see well above the
# walls at the top of the jump.
JUMP_SPEED = 5.5 * 3  # = 16.5
GRAVITY = -14.0

# --- Effects ---
MIN_EFFECT_COUNT = 6  # minimum instances of EACH trap/powerup type
MAX_EFFECT_COUNT = 9  # maximum instances of EACH trap/powerup type

# --- Audio ---
MUSIC_FILE = "background_music.wav"          # normal background track
MUSHROOM_MUSIC_FILE = "mushroom_music.wav"   # plays during the Magic Mushroom effect
MONSTER_MUSIC_FILE = "monster_near_music.wav"  # plays while the monster is nearby
VICTORY_MUSIC_FILE = "victory_music.wav"     # plays once the goal is reached
MUSIC_VOLUME = 0.5  # 0.0 (silent) to 1.0 (full volume)

# Hysteresis: the EXIT radius is deliberately larger than the TRIGGER
# radius. Without this gap, hovering right at a single boundary
# distance would flicker the music back and forth every frame the
# monster's position crosses it by a hair.
MONSTER_MUSIC_TRIGGER_RADIUS = 20.0  # world units - switches TO the tense track within this range
MONSTER_MUSIC_EXIT_RADIUS = 26.0     # world units - switches BACK once farther than this

# --- Monster (loosely inspired by the La Llorona legend) ---
MONSTER_ICON = "llorona.png"
MONSTER_BILLBOARD_SIZE = 2.4          # taller than powerup icons - roughly human-sized
MONSTER_MOVE_SPEED = 1.6              # cells per second, at range
MONSTER_MAX_MOVE_SPEED = 3.2          # cells per second, once very close (faster than the player!)
MONSTER_SPEED_RAMP_RADIUS = 6.0       # world units - speed ramps up smoothly within this distance
MONSTER_PATH_REFRESH_SECONDS = 1.0    # how often her chase path recalculates
MONSTER_CATCH_RADIUS = 0.9            # world units - how close counts as "caught"
MONSTER_CAUGHT_FREEZE_SECONDS = 4.0   # how long you're frozen in fright after being caught
MONSTER_CATCH_COOLDOWN_SECONDS = 3.0  # brief invulnerability right after being caught
MONSTER_MIN_SPAWN_DISTANCE = 25       # cells - keeps her spawn away from the player's start
MONSTER_CATCH_SOUND = "monster_catch.wav"  # plays the moment she catches the player
MONSTER_SCREAM_SOUND = "monster_scream.wav"  # plays ALONGSIDE the catch sound, not instead of it

# --- Portal (teleport trap) visual transition ---
TELEPORT_FLASH_DURATION = 0.6    # seconds - how long the flash takes to fade out
TELEPORT_FLASH_MAX_ALPHA = 0.85  # how opaque the flash is at its peak, right when triggered
TELEPORT_FLASH_COLOR = (0.6, 0.2, 0.9)  # matches the teleport trap's purple reveal color

# --- Jumpscare (on being caught) ---
JUMPSCARE_IMAGE = "jumpscare.png"
JUMPSCARE_DURATION = 4.0  # seconds the image stays on screen before respawning at the start

MONSTER_CRY_FILES = [
    "llorona_scream_one.wav",
    "llorona_scream_two.wav",
    "llorona_scream_three.wav",
    "llorona_scream_four.wav",
]
MONSTER_CRY_MIN_INTERVAL_SECONDS = 15.0  # minimum gap between cries, regardless of distance
MONSTER_CRY_TRIGGER_RADIUS = 15.0        # world units - she only cries out when within this range
MONSTER_CRY_MAX_VOLUME = 0.8

# --- Minimap ---
MINIMAP_ITEM_DOT_SCALE = 1.3    # powerup marker size, relative to a cell's half-width
MINIMAP_MONSTER_DOT_SCALE = 1.6  # slightly bigger than item markers - she's the bigger threat