"""
Background music. Uses pygame's mixer module, which is separate from
the OpenGL/Pygame display code entirely - loading and playing music
has nothing to do with rendering, so this stays its own small module.
"""

import pygame
import random

import config

_mixer_ready = False


def _play_track(filename, volume):
    """
    Loads and plays a single music file on loop. pygame.mixer.music is
    a STREAMING API meant for exactly one track at a time - loading a
    new file automatically stops whatever was playing before, which is
    exactly the behavior we want for swapping to/from the mushroom
    effect's music.
    """
    global _mixer_ready
    if not _mixer_ready:
        return
    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(loops=-1)  # -1 = loop forever
    except pygame.error as e:
        print(f"Could not play {filename}: {e}")


def init_music():
    """
    Sets up the mixer and starts the normal background track.

    Wrapped in try/except because audio can fail for reasons that
    shouldn't crash the game: no audio device present, the music file
    missing, an unsupported format, etc. If anything goes wrong, we
    print a warning and continue running WITHOUT music, rather than
    stopping the player from playing at all over something cosmetic.
    """
    global _mixer_ready, _music_state
    try:
        pygame.mixer.init()
        _mixer_ready = True
    except pygame.error as e:
        print(f"Audio disabled: {e}")
        return

    _play_track(config.MUSIC_FILE, config.MUSIC_VOLUME)
    _music_state = "normal"


# ---------------------------------------------------------
# BACKGROUND MUSIC STATE
# ---------------------------------------------------------
# Two different things can each want their own background track: the
# mushroom effect, and the monster being nearby. Rather than having
# both call separate "play_x_music()" functions independently (which
# could fight over control of the single music channel - whichever
# called last would win, even if the "wrong" one), this is the ONE
# place that decides what SHOULD be playing, with an explicit
# priority order, and only actually switches tracks when that answer
# changes from last time it was checked.
_music_state = "normal"  # "normal", "monster_near", or "mushroom"


def update_background_music(mushroom_active, monster_near):
    """
    Call this once per frame with the current mushroom/monster state.
    Mushroom takes priority over monster-proximity if both happen to
    be true at once.
    """
    global _music_state

    if mushroom_active:
        desired_state = "mushroom"
    elif monster_near:
        desired_state = "monster_near"
    else:
        desired_state = "normal"

    if desired_state == _music_state:
        return  # already playing the right track - nothing to do

    _music_state = desired_state
    if desired_state == "mushroom":
        _play_track(config.MUSHROOM_MUSIC_FILE, config.MUSIC_VOLUME)
    elif desired_state == "monster_near":
        _play_track(config.MONSTER_MUSIC_FILE, config.MUSIC_VOLUME)
    else:
        _play_track(config.MUSIC_FILE, config.MUSIC_VOLUME)


def play_victory_music():
    """
    Called once, the moment the player reaches the goal. Stops
    EVERYTHING currently playing - not just the background music, but
    any one-shot sound effects still finishing up too (a pickup chime,
    the monster's cry, footsteps, etc.) - then starts the victory
    track.

    Sets _music_state to "victory", a state update_background_music()
    never chooses on its own - so as long as the caller stops calling
    update_background_music() once the game is finished (main.py does
    this), the victory track keeps playing uninterrupted until the
    next reset.
    """
    global _music_state
    if not _mixer_ready:
        return
    pygame.mixer.stop()  # stops every Sound channel - pickups, cries, catch, scream, etc.
    _play_track(config.VICTORY_MUSIC_FILE, config.MUSIC_VOLUME)
    _music_state = "victory"


_cry_sounds = []       # every successfully-loaded cry variant
_cry_shuffle_bag = []  # remaining picks before the next reshuffle


def load_monster_sound():
    """
    Loads every one of the monster's cry variants (config.MONSTER_CRY_FILES)
    as separate pygame.mixer.Sound objects - a different API from
    pygame.mixer.music above. music is a STREAMING player meant for
    exactly one long background track; Sound is for short one-shot
    effects loaded fully into memory, and can play on its own channel
    ALONGSIDE whatever music is already playing, rather than replacing
    it. Having several loaded is what lets play_monster_cry() rotate
    between them instead of always playing the same clip.
    """
    global _cry_sounds
    _cry_sounds = []
    if not _mixer_ready:
        return
    for filename in config.MONSTER_CRY_FILES:
        try:
            _cry_sounds.append(pygame.mixer.Sound(filename))
        except pygame.error as e:
            print(f"Monster cry sound disabled ({filename}): {e}")


def play_monster_cry(volume):
    """
    Plays a randomly-chosen cry clip, using a "shuffle bag": all
    loaded clips get shuffled into a queue, and each play pops one off
    it. Once the bag empties, it's refilled and reshuffled. This
    guarantees every clip gets heard before any of them repeats,
    unlike calling random.choice() fresh each time, which could
    occasionally play the same clip twice (or more) in a row.
    """
    global _cry_shuffle_bag
    if not _cry_sounds:
        return

    if not _cry_shuffle_bag:
        _cry_shuffle_bag = _cry_sounds.copy()
        random.shuffle(_cry_shuffle_bag)

    sound = _cry_shuffle_bag.pop()
    sound.set_volume(max(0.0, min(1.0, volume)))
    sound.play()


# ---------------------------------------------------------
# EFFECT (TRAP/POWERUP) SOUND EFFECTS
# ---------------------------------------------------------
# One pygame.mixer.Sound per unique filename, cached by filename so
# the same file is never loaded from disk twice - several different
# effect templates could reference the same sound if you want.
_sound_cache = {}


def load_effect_sounds(filenames):
    """
    Preloads every sound file referenced across all effect templates,
    once at startup. Loading ahead of time (rather than the first time
    each effect triggers) avoids a disk-read hitch the first time a
    player steps on any particular trap/powerup mid-game.
    """
    if not _mixer_ready:
        return
    for filename in filenames:
        if filename in _sound_cache:
            continue
        try:
            _sound_cache[filename] = pygame.mixer.Sound(filename)
        except pygame.error as e:
            print(f"Effect sound disabled ({filename}): {e}")


def play_effect_sound(filename, volume=1.0):
    sound = _sound_cache.get(filename)
    if sound is None:
        return  # never loaded (missing file, or audio disabled) - just skip silently
    sound.set_volume(max(0.0, min(1.0, volume)))
    sound.play()