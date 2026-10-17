"""BUG-201: the shadow cache's real-run bound (utils/graphics.py docs): one Game, many encounters, no per-Game clear."""
from __future__ import annotations

import random

import pygame
import pytest

from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.utils.enums import GameState, NodeType
from blob_evolution.utils.graphics import SHADOW_CACHE_REAL_RUN_BYTES, get_graphics_cache

TYPES = (NodeType.FIGHT, NodeType.ELITE, NodeType.MINIBOSS, NodeType.BOSS)


def _shadow_bytes() -> int:
    return sum(s.get_width() * s.get_height() * 4 for s in get_graphics_cache()._shadows.values())


def _play(game, seconds: float) -> None:
    dt = 1 / 60
    for frame in range(int(seconds * 60)):
        game.state = GameState.PLAYING
        game.player.hp = game.player.max_hp
        foes = [c for c in game.creatures if c.active] + [b for b in game.bosses if b.active]
        if not foes:
            return
        tgt = min(foes, key=lambda c: c.pos.distance_to(game.player.pos))
        d = tgt.pos - game.player.pos
        if d.length() > 220:
            game.player.pos.add(d.normalize() * (game.player.speed * dt * 0.8))
        game.player.shoot(tgt.pos, game.projectiles)
        game._update(dt)
        if frame % 6 == 0:
            game._draw_game()


@pytest.fixture
def game(make_game, monkeypatch):
    g = make_game()                                        # the only Game: its one clear happens here, never again
    for name in ("play", "play_act_music", "play_menu_music", "play_narration"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    random.seed(2026)
    g._start_new_run()
    g.story = None
    return g


def test_a_ten_layer_session_keeps_the_shadow_cache_within_its_real_run_bound(game, monkeypatch):
    clears = []
    monkeypatch.setattr(type(get_graphics_cache()), "clear", lambda self: clears.append(1))
    peak = 0
    for act in range(10):
        game.overworld = OverworldMap(act_index=act, seed=11 + act)
        for kind in TYPES:
            node = next((n for n in game.overworld.nodes.values() if n.node_type == kind), None)
            if node is None:
                continue
            game._load_encounter(node)
            while game.state == GameState.STORY:
                game._advance_story()
            _play(game, 2.0)
            peak = max(peak, _shadow_bytes())
    assert not clears, "the session must run without any shadow cache clear"
    assert get_graphics_cache().shadow_count() > 20, "a real session fills the cache (else the bound is untested)"
    assert peak <= SHADOW_CACHE_REAL_RUN_BYTES == 1_500_000, peak
