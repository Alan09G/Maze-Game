import math
import time

import pygame
from pygame.locals import DOUBLEBUF, OPENGL, QUIT
from OpenGL.GL import *
from OpenGL.GLU import *

import config
import maze
import audio
from player import Player
from monster import Monster
from effects import EFFECTS, EFFECT_TEMPLATES, EffectManager
from textures import (load_texture, load_icon_texture, generate_glow_surface,
                      generate_night_sky_surface, surface_to_texture)
from render_world import (draw_maze, draw_tile_tint, draw_goal_beacon, draw_path_highlight,
                          draw_visible_traps, draw_skybox)
from render_icons import draw_effect_icons, draw_ghost_billboard
from ui import (draw_win_popup, draw_effect_message, draw_hud_timer, draw_screen_tint,
                draw_minimap, draw_psychedelic_overlay, draw_stamina_bar,
                draw_jumpscare, clear_text_cache)


def main():
    pygame.init()
    pygame.font.init()
    audio.init_music()
    audio.load_monster_sound()

    # Preload every unique sound referenced across ALL templates (not
    # just the ones that happened to spawn this run) - dedupes
    # automatically via the set(), and avoids a disk-read hitch the
    # first time any particular trap/powerup triggers mid-game.
    effect_sound_filenames = {t["sound"] for t in EFFECT_TEMPLATES if "sound" in t}
    effect_sound_filenames.add(config.MONSTER_CATCH_SOUND)
    effect_sound_filenames.add(config.MONSTER_SCREAM_SOUND)
    audio.load_effect_sounds(effect_sound_filenames)
    pygame.display.set_mode((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("3D Maze")

    glEnable(GL_DEPTH_TEST)
    glClearColor(*config.SKY_COLOR, 1.0)

    # Fog: fixed-function OpenGL has this built in - no shaders needed.
    # Its color matches SKY_COLOR so distant geometry fades smoothly
    # into the night sky rather than just vanishing, and its END
    # distance is tuned to sit just past VIEW_RADIUS*CELL_SIZE, so it
    # also softens the abrupt pop-in/out at the edge of the maze's
    # view-distance culling window.
    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_LINEAR)
    glFogfv(GL_FOG_COLOR, (*config.SKY_COLOR, 1.0))
    glFogf(GL_FOG_START, config.FOG_START)
    glFogf(GL_FOG_END, config.FOG_END)
    glHint(GL_FOG_HINT, GL_NICEST)

    # --- Lighting: a single directional "moonlight" light ---
    # GL_LIGHTING itself (the master switch) is deliberately NOT
    # enabled here - it's only ever turned on inside draw_maze()'s cube
    # loop and turned back off before that function returns, so
    # everything else in the frame (icons, HUD, skybox, etc.) is
    # automatically unaffected without needing individual disables.
    glEnable(GL_LIGHT0)
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, config.AMBIENT_LIGHT)
    glLightfv(GL_LIGHT0, GL_AMBIENT, (0.0, 0.0, 0.0, 1.0))  # ambient comes from the LIGHT MODEL above, not per-light
    glLightfv(GL_LIGHT0, GL_DIFFUSE, config.MOON_LIGHT_DIFFUSE)
    glLightfv(GL_LIGHT0, GL_SPECULAR, (0.0, 0.0, 0.0, 1.0))  # no shiny highlights needed

    # Lets our existing glColor3f()/glColor4f() calls - used everywhere
    # already: the moonlight tint, effect colors, HUD panels - double
    # as the lit material's color, instead of needing every draw call
    # rewritten to use glMaterial() explicitly.
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

    # Projection (including FOV) is set fresh every frame in the render
    # loop below, rather than once here - the mushroom effect needs to
    # pulse the FOV over time, which means recomputing this matrix
    # continuously rather than setting it up once and leaving it fixed.
    glMatrixMode(GL_MODELVIEW)

    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)

    wall_texture = load_texture('wall')
    floor_texture = load_texture('floor')
    sky_texture, _, _ = surface_to_texture(generate_night_sky_surface(star_count=config.STAR_COUNT))

    icon_filenames = {effect["icon"] for effect in EFFECTS.values() if "icon" in effect}
    icon_textures = {filename: load_icon_texture(filename) for filename in icon_filenames}
    glow_texture, _, _ = surface_to_texture(generate_glow_surface())
    monster_texture = load_icon_texture(config.MONSTER_ICON)
    jumpscare_texture = load_icon_texture(config.JUMPSCARE_IMAGE)

    font_big = pygame.font.SysFont("arial", 28, bold=True)
    font_medium = pygame.font.SysFont("arial", 22, bold=True)
    font_small = pygame.font.SysFont("arial", 20)

    player = Player(
        x=(maze.START_COL + 0.5) * config.CELL_SIZE,
        y=config.GROUND_Y,
        z=(maze.START_ROW + 0.5) * config.CELL_SIZE,
    )
    effect_manager = EffectManager()
    monster = Monster()

    PLAYING, FINISHED = "playing", "finished"
    state = PLAYING
    start_time = time.time()
    final_time = None
    monster_cooldown_until = 0.0  # brief invulnerability window right after being caught
    monster_music_near = False    # hysteresis state for the proximity music switch
    awaiting_respawn = False      # True while the jumpscare image is showing, pre-respawn
    jumpscare_end_time = 0.0      # time.time() value at which the delayed respawn happens

    def reset_game():
        nonlocal state, start_time, final_time, monster_cooldown_until, monster_music_near
        nonlocal awaiting_respawn, jumpscare_end_time
        player.reset(
            x=(maze.START_COL + 0.5) * config.CELL_SIZE,
            z=(maze.START_ROW + 0.5) * config.CELL_SIZE,
            ground_y=config.GROUND_Y,
        )
        effect_manager.reset()
        monster.reset()
        state = PLAYING
        start_time = time.time()
        final_time = None
        monster_cooldown_until = 0.0
        monster_music_near = False
        awaiting_respawn = False
        jumpscare_end_time = 0.0
        clear_text_cache()
        pygame.mouse.get_rel()

    clock = pygame.time.Clock()
    running = True

    while running:
        dt = clock.tick(60) / 1000.0
        now = time.time()

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r and state == FINISHED:
                reset_game()
            if (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE
                    and state == PLAYING and player.jump_charges > 0
                    and not player.is_jumping and not effect_manager.is_frozen(now)
                    and not awaiting_respawn):
                player.start_jump(config.JUMP_SPEED)

        # Delayed respawn: once the jumpscare has been showing long
        # enough, send the player back to the START of the maze (not
        # a random cell, unlike the teleport trap). Checked every
        # frame, independent of the state==PLAYING gating below, so
        # it fires exactly once the instant the duration elapses.
        if awaiting_respawn and now >= jumpscare_end_time:
            player.x = (maze.START_COL + 0.5) * config.CELL_SIZE
            player.z = (maze.START_ROW + 0.5) * config.CELL_SIZE
            awaiting_respawn = False

        is_frozen = False  # default for rendering below, in case state isn't PLAYING

        if state == PLAYING:
            mouse_dx, mouse_dy = pygame.mouse.get_rel()
            player.yaw += mouse_dx * config.MOUSE_SENSITIVITY
            player.pitch -= mouse_dy * config.MOUSE_SENSITIVITY
            player.pitch = max(-89.0, min(89.0, player.pitch))

            effect_manager.update_expiry(now)
            # Movement stays locked for the entire jumpscare sequence,
            # not just while effect_manager's own freeze effect is
            # active - awaiting_respawn folds into the same gate so
            # nothing else needs to check it separately.
            is_frozen = effect_manager.is_frozen(now) or awaiting_respawn

            if not is_frozen:
                keys = pygame.key.get_pressed()
                move_x, move_z = 0.0, 0.0
                fx, _, fz = player.forward_vector()
                rx, rz = player.right_vector()

                if keys[pygame.K_w]:
                    move_x += fx; move_z += fz
                if keys[pygame.K_s]:
                    move_x -= fx; move_z -= fz
                if keys[pygame.K_a]:
                    move_x -= rx; move_z -= rz
                if keys[pygame.K_d]:
                    move_x += rx; move_z += rz

                length = math.hypot(move_x, move_z)
                if length > 0:
                    is_sprinting = (
                        (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
                        and effect_manager.has_stamina()
                    )
                    speed_multiplier = effect_manager.speed_multiplier
                    if is_sprinting:
                        speed_multiplier *= config.STAMINA_SPRINT_MULTIPLIER
                        effect_manager.consume_stamina(dt)

                    effective_speed = config.BASE_MOVE_SPEED * speed_multiplier
                    move_x = (move_x / length) * effective_speed * dt
                    move_z = (move_z / length) * effective_speed * dt
                    player.x, player.z = maze.try_move(player.x, player.z, move_x, move_z)
            # else: frozen (or mid-jumpscare) - mouse-look still works
            # above, but no horizontal movement is processed this frame.

            # Vertical jump physics runs independently of is_frozen: a
            # jump already in progress still finishes even if a freeze
            # trap triggers mid-air.
            player.update_vertical_physics(dt, config.GRAVITY, config.GROUND_Y)

            position = maze.world_to_cell(player.x, player.z)
            if not awaiting_respawn:
                effect_manager.check_tile(position, now, player)

            monster.update(dt, now, position[0], position[1], player.x, player.z)
            if (now >= monster_cooldown_until and not awaiting_respawn
                    and monster.is_touching_player(player.x, player.z)):
                # "Caught": freeze immediately, show the jumpscare image
                # for JUMPSCARE_DURATION seconds, THEN respawn at the
                # maze's start (handled by the delayed-respawn check
                # above, once jumpscare_end_time is reached). A cooldown
                # also starts now so she can't immediately re-trigger
                # this the instant the player reappears nearby.
                audio.play_effect_sound(config.MONSTER_CATCH_SOUND)
                audio.play_effect_sound(config.MONSTER_SCREAM_SOUND)
                jumpscare_end_time = now + config.JUMPSCARE_DURATION
                awaiting_respawn = True
                monster_cooldown_until = now + config.MONSTER_CATCH_COOLDOWN_SECONDS

            if not awaiting_respawn and maze.reached_goal(player.x, player.z):
                state = FINISHED
                final_time = now - start_time
                audio.play_victory_music()
        else:
            pygame.mouse.get_rel()

        # --- Render 3D scene ---
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        mushroom_active = effect_manager.is_mushroom_active(now)

        # Hysteresis: only flip to "near" once within the (smaller)
        # trigger radius, and only flip back once past the (larger)
        # exit radius - prevents the music rapidly toggling back and
        # forth if she's hovering right around one single boundary.
        distance_to_monster = math.hypot(monster.x - player.x, monster.z - player.z)
        if monster_music_near:
            if distance_to_monster > config.MONSTER_MUSIC_EXIT_RADIUS:
                monster_music_near = False
        else:
            if distance_to_monster <= config.MONSTER_MUSIC_TRIGGER_RADIUS:
                monster_music_near = True

        # Only drive the normal priority-based music switching while
        # actually playing - once FINISHED, play_victory_music() already
        # set a "victory" state above that this call would otherwise
        # immediately override back to normal/monster-near music.
        if state == PLAYING:
            audio.update_background_music(mushroom_active, monster_music_near)

        # FOV pulse: normally a fixed 70 degrees, but oscillates during
        # the mushroom effect for a "breathing" zoom distortion. Far
        # clip plane is 300 (not the original 100) so the goal beacon,
        # which ignores view-distance culling, stays visible at range.
        fov = 70.0
        if mushroom_active:
            fov += math.sin(now * 4.0) * 15.0
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(fov, config.DISPLAY_WIDTH / config.DISPLAY_HEIGHT, 0.1, 300.0)
        glMatrixMode(GL_MODELVIEW)

        glLoadIdentity()

        # Camera wobble: small oscillating yaw/pitch OFFSETS applied only
        # to this frame's rendered view direction - player.yaw/pitch (the
        # actual stored orientation used for movement) are untouched, so
        # the screen shakes without affecting controls at all.
        if mushroom_active:
            wobble_yaw = math.sin(now * 2.2) * 6.0
            wobble_pitch = math.sin(now * 3.1) * 4.0
        else:
            wobble_yaw = wobble_pitch = 0.0
        player.apply_look_at(wobble_yaw, wobble_pitch)

        # The moonlight direction is fixed in WORLD space (a real moon
        # doesn't move as you turn your head) - setting it HERE, AFTER
        # the view transform above, is what makes that correct: OpenGL
        # transforms whatever we pass by the CURRENT modelview matrix,
        # so passing the world-space direction now correctly
        # re-expresses it in eye-space for this frame's camera
        # orientation. (This is the opposite order from a camera-
        # attached "headlamp" light, which would need to be set BEFORE
        # the view transform instead.)
        glLightfv(GL_LIGHT0, GL_POSITION, config.MOON_LIGHT_DIRECTION)

        # Skybox - drawn first, translated to the camera's OWN position
        # (see draw_skybox()'s docstring for why that makes it appear
        # infinitely far away regardless of where the player walks).
        glPushMatrix()
        glTranslatef(player.x, player.y, player.z)
        draw_skybox(sky_texture, config.SKYBOX_SIZE)
        glPopMatrix()

        player_row, player_col = maze.world_to_cell(player.x, player.z)

        # Horizontal-only forward direction (yaw only, ignoring pitch) -
        # used for facing-direction culling in draw_maze(). Using the
        # camera's actual pitch-affected forward vector here would
        # incorrectly cull almost everything while looking steeply up
        # or down (e.g. mid-jump).
        cull_yaw_rad = math.radians(player.yaw)
        cull_forward_x = math.sin(cull_yaw_rad)
        cull_forward_z = -math.cos(cull_yaw_rad)
        draw_maze(wall_texture, floor_texture, player_row, player_col,
                  player.x, player.z, cull_forward_x, cull_forward_z, config.VIEW_RADIUS)
        draw_visible_traps(effect_manager.active_effects, player_row, player_col)

        spin_degrees = (now * 90) % 360  # 90 degrees per second, time-based not frame-based
        draw_effect_icons(effect_manager.active_effects, icon_textures, glow_texture, spin_degrees, now)

        draw_ghost_billboard(monster.x, monster.z, config.MONSTER_BILLBOARD_SIZE, monster_texture, now)

        if effect_manager.frozen_tile_position is not None and effect_manager.is_frozen(now):
            draw_tile_tint(*effect_manager.frozen_tile_position, color_rgba=(0.2, 0.5, 0.95, 0.55))

        if effect_manager.is_goal_revealed(now):
            draw_goal_beacon(maze.GOAL_ROW, maze.GOAL_COL, now)

        if effect_manager.is_path_revealed(now):
            draw_path_highlight(effect_manager.revealed_path, player_row, player_col,
                                 color_rgba=(0.7, 0.4, 1.0, 0.5))

        if is_frozen:
            draw_screen_tint(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, (0.1, 0.35, 0.85, 0.22))

        flash_alpha = effect_manager.teleport_flash_alpha(now)
        if flash_alpha > 0:
            draw_screen_tint(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT,
                              (*config.TELEPORT_FLASH_COLOR, flash_alpha))

        if mushroom_active:
            draw_psychedelic_overlay(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, now)

        displayed_time = final_time if state == FINISHED else (now - start_time)
        draw_hud_timer(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, displayed_time, font_medium)

        stamina_fraction = effect_manager.stamina / config.STAMINA_MAX_SECONDS
        draw_stamina_bar(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, stamina_fraction, font_small)

        # Fractional row/col (not floor()'d) since she moves smoothly
        # between cells - this keeps her minimap marker in sync with
        # her actual interpolated position instead of visibly snapping
        # each time she enters a new cell.
        monster_frac_row = monster.z / config.CELL_SIZE - 0.5
        monster_frac_col = monster.x / config.CELL_SIZE - 0.5

        draw_minimap(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, player_row, player_col,
                     player.yaw, effect_manager.active_effects,
                     show_goal_arrow=effect_manager.is_goal_revealed(now),
                     monster_row=monster_frac_row, monster_col=monster_frac_col)

        if effect_manager.current_message is not None and now < effect_manager.message_until:
            name, message = effect_manager.current_message
            draw_effect_message(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, name, message,
                                 font_medium, font_small)

        if state == FINISHED:
            draw_win_popup(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, final_time, font_big, font_small)

        # Drawn absolute LAST: fully covers the 3D scene and every
        # other HUD element the instant she catches the player, for
        # the full JUMPSCARE_DURATION.
        if awaiting_respawn:
            draw_jumpscare(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, jumpscare_texture)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()