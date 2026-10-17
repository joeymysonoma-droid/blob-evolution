"""TASK-059: a fixed, seeded fight scene hashed frame by frame. Runs on this branch and on the pre-059 build
(merge08-fixes d38cc49), so GFX_HITFX = False can be proven pixel identical to the current build.

Scene (act `act`, 240 frames at 60 fps): a shielder, a basic, a bomber and a charging charger overlapping the player,
a warden; player shots at the creatures and the boss every 4 frames, enemy shots at the player every 13 frames, an XP
orb on the player at frame 50. Drawn every 8 frames; the digest covers every drawn frame."""
from __future__ import annotations

import hashlib
import random

import pygame

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.creature import Creature
from blob_evolution.entities.pickups import XPOrb
from blob_evolution.entities.projectile import Projectile
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.utils.enums import CreatureType, GameState, NodeType
from blob_evolution.utils.vector2 import Vector2

FRAMES = 240
DRAW_EVERY = 8
DT = 1 / 60


def make_scene_game(act: int = 0):
    from blob_evolution.game import Game
    g = Game()
    sounds = []
    g.audio.play = lambda name, scale=1.0: sounds.append((name, scale))
    g.audio.play_act_music = lambda act: None
    g.audio.play_menu_music = lambda: None
    g._start_new_run()
    g.story = None
    g.overworld = OverworldMap(act_index=act, seed=7)
    node = next(n for n in g.overworld.nodes.values() if n.node_type == NodeType.FIGHT)
    random.seed(1234)
    g._load_encounter(node)
    g.state = GameState.PLAYING
    g.sounds = sounds
    return g


def run_scene(act: int = 0, frames: int = FRAMES, record=None):
    """-> (digest of every drawn frame, the game). `record(game, f)` is called after each frame if given."""
    from blob_evolution.utils import clock
    clock.reset()                                         # animation clocks are module globals: start from 0
    g = make_scene_game(act)
    random.seed(77)
    p = g.player
    p.pos.set(1000, 1000)
    p.max_hp = p.hp = 1e9
    g.creatures = [Creature(Vector2(1160, 980), CreatureType.SHIELDER, size=22),
                   Creature(Vector2(860, 1080), CreatureType.BASIC, size=18),
                   Creature(Vector2(1100, 860), CreatureType.BOMBER, size=16),
                   Creature(Vector2(1010, 1005), CreatureType.CHARGER, size=30)]
    for c in g.creatures:
        c.max_hp = c.hp = 400.0
        c.speed = 0.0
    g.creatures[2].hp = 30.0
    b = Boss(Vector2(1250, 1150), act, None)
    b.speed = 0.0
    b.max_hp = b.hp = 1e7                                 # the fight never ends inside the scene
    g.bosses = [b]
    g.projectiles, g.xp_orbs = [], []
    g.camera.set(1000, 1000)
    h = hashlib.sha1()
    for f in range(frames):
        p.max_hp = p.hp = 1e9                             # level-ups recompute max_hp; nothing ends the scene
        for c in g.creatures:
            if c.ctype == CreatureType.CHARGER and c.active:
                c.charging = True
                c.pos.set(1010, 1005)
        if f % 4 == 0:
            for t in [c for c in g.creatures if c.active][:3] + [x for x in g.bosses if x.active]:
                g.projectiles.append(Projectile(t.pos + Vector2(t.radius + 2, -3), Vector2(-1, 0), 0, 10, from_player=True))
        if f % 13 == 5:
            g.projectiles.append(Projectile(p.pos + Vector2(4, 0), Vector2(1, 0), 0, 3, from_player=False))
        if f == 50:
            g.xp_orbs.append(XPOrb(p.pos.copy(), 5000))
        g._update(DT)
        if f % DRAW_EVERY == 0:
            g._draw()
            h.update(pygame.image.tobytes(g.screen, "RGB"))
        if record:
            record(g, f)
    return h.hexdigest()[:16], g


if __name__ == "__main__":
    import sys
    for act in (0, 5, 9):
        print(act, run_scene(act)[0])
        sys.stdout.flush()
