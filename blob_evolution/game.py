"""Main game loop and state management."""

from __future__ import annotations

import math
import random
from typing import List, Optional

import pygame

from blob_evolution import config
from blob_evolution.data.lore import (
    ARCHIVE_TABS,
    BLACKSMITH_SUBTITLE,
    BLACKSMITH_TITLE,
    REST_SUBTITLE,
    REST_TITLE,
    archive_entries_for_tab,
    build_act_descent_pages,
    build_boss_intro_pages,
    build_pilgrimage_pages,
    get_act_journal,
    get_act_lore,
    get_artifact_blurb,
    get_artifact_lineage_name,
    get_warden_fragment_id,
    wrap_text,
)
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.creature import Creature
from blob_evolution.entities.particle import ParticleSystem
from blob_evolution.entities.pickups import XPOrb
from blob_evolution.entities.player import Player
from blob_evolution.entities.projectile import Projectile
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.systems import savefile
from blob_evolution.systems.artifacts import ARTIFACT_DEFINITIONS, ArtifactManager
from blob_evolution.systems.audio import get_audio
from blob_evolution.systems.economy import EconomyManager, SHOP_ITEMS
from blob_evolution.systems.events import EventManager
from blob_evolution.systems.hazards import HazardManager
from blob_evolution.systems.newgameplus import NewGamePlus
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.systems.permanent import PERMANENT_UPGRADES, SKINS, PermanentProgress
from blob_evolution.systems.skills import SKILL_ORDER
from blob_evolution.ui import style
from blob_evolution.ui.cinematic import CinematicRenderer, StoryPage, StorySequence
from blob_evolution.ui.hud import HUD
from blob_evolution.ui.menus import MenuRenderer
from blob_evolution.ui.overworld_map import OverworldRenderer
from blob_evolution.utils.enums import CreatureType, Difficulty, GameState, NodeType
from blob_evolution.utils.vector2 import Vector2


class Game:
    """Main game controller."""

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption(config.TITLE)
        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.state = GameState.MAIN_MENU
        self.difficulty = Difficulty.NORMAL
        self.menu = MenuRenderer()
        self.hud = HUD()
        self.cinematic = CinematicRenderer()
        self.story: Optional[StorySequence] = None
        self.audio = get_audio()
        self.map_gen = MapGenerator()
        self.hazards = HazardManager()
        self.economy = EconomyManager()
        self.ng_plus = NewGamePlus()
        self.permanent = PermanentProgress()
        self.particles = ParticleSystem()
        self.overworld: Optional[OverworldMap] = None
        self.overworld_renderer = OverworldRenderer()
        self.event_manager = EventManager()
        self.current_node_params: dict = {}
        self.run_shards_earned = 0
        self.overworld_selected = 0
        self.event_choice = 0
        self.blacksmith_selected = 0
        self.meta_selected = 0
        self.meta_tab = 0  # 0=upgrades, 1=skins
        self.meta_scroll = 0
        self.archive_tab = 0
        self.archive_selected = 0
        self.core_choice_selected = 0
        self.run_ending = "reopen"
        self._boss_touch_cooldown = 0.0
        self._ambient_timer = 0.0
        self._seen_acts: set = set()
        self._shoot_sound_cd = 0.0
        self.audio.play_menu_music()

        self.player: Optional[Player] = None
        self.creatures: List[Creature] = []
        self.bosses: List[Boss] = []
        self.projectiles: List[Projectile] = []
        self.xp_orbs: List[XPOrb] = []

        self.camera = Vector2()
        self.camera_target = Vector2()
        self.shake = Vector2()
        self.shake_intensity = 0.0

        self.menu_selected = 0
        self.pause_selected = 0
        self.game_over_selected = 0
        self.victory_selected = 0
        self.shop_selected = 0
        self.options_selected = 0
        self.maps_cleared = 0
        self.run_stats: dict = {}
        self.fps = 60.0
        self._load_save()

    def _load_save(self) -> None:
        """Load persistent save data; back up the file first if any of it is unusable."""
        self._save_blocked = False
        data = savefile.read_save(config.SAVE_FILE)
        readable = data is not None
        data = data if readable else {}
        ng_ok = self.ng_plus.from_dict(data.get("ng_plus", {}))
        perm_ok = self.permanent.from_dict(data.get("permanent", {}))
        eco = savefile.SaveSection(data.get("economy", {}))
        self.economy.total_earned = eco.number("total_earned", 0)
        if "audio_enabled" in data:
            self.audio.set_enabled(bool(data["audio_enabled"]))
            if self.audio.enabled:
                self.audio.play_menu_music()
        if not (readable and ng_ok and perm_ok and eco.valid):
            if readable:
                savefile.warn(f"{config.SAVE_FILE} has invalid data; using defaults for those parts")
            self._save_blocked = not savefile.backup_save(config.SAVE_FILE)

    def _save_game(self) -> None:
        """Save persistent progress, unless an unreadable save couldn't be backed up."""
        if self._save_blocked:
            if not savefile.backup_save(config.SAVE_FILE):
                return
            self._save_blocked = False
        data = {
            "ng_plus": self.ng_plus.to_dict(),
            "permanent": self.permanent.to_dict(),
            "economy": {"essence": 0, "total_earned": self.economy.total_earned,
                        "run_damage_boost": 0.0},
            "audio_enabled": self.audio.enabled,
        }
        savefile.write_save(config.SAVE_FILE, data)

    def _diff_mult(self) -> dict:
        """Get difficulty multipliers."""
        return config.DIFFICULTY_SETTINGS[self.difficulty.value]

    def _apply_permanent_bonuses(self) -> None:
        """Apply permanent upgrade bonuses to player."""
        if not self.player:
            return
        self.player.perm_bonuses = {
            "damage": 1.0 + self.permanent.get_bonus("damage"),
            "health": 1.0 + self.permanent.get_bonus("health"),
            "speed": 1.0 + self.permanent.get_bonus("speed"),
            "essence": 1.0 + self.permanent.get_bonus("essence"),
            "xp": 1.0 + self.permanent.get_bonus("xp"),
            "magnet": 1.0 + self.permanent.get_bonus("magnet"),
            "armor": self.permanent.get_flat("armor"),
            "lifesteal": self.permanent.get_flat("lifesteal"),
            "crit": self.permanent.get_flat("crit"),
            "luck": self.permanent.get_flat("luck"),
        }
        color, core = self.permanent.get_skin_colors()
        self.player.skin_color = color
        self.player.skin_core = core
        self.player._update_stats()

    def _award_shards(self, amount: int) -> None:
        """Award shards for current run and permanent pool."""
        self.run_shards_earned += amount

    def _start_story(self, page_dicts: list, resume_state: GameState) -> None:
        """Begin a cinematic story sequence."""
        pages = []
        for p in page_dicts:
            accent = p.get("accent", style.ACCENT)
            pages.append(StoryPage(
                title=p["title"],
                body=p["body"],
                accent=accent,
                eyebrow=p.get("eyebrow", ""),
                blob_color=accent,
                blob_core=style.lerp_color(accent, (255, 255, 255), 0.35),
            ))
        self.story = StorySequence(pages=pages, resume_state=resume_state)
        self.state = GameState.STORY

    def _advance_story(self) -> None:
        """Advance or finish the current story sequence."""
        if not self.story:
            self.state = GameState.OVERWORLD
            return
        self.audio.play("story")
        if self.story.advance():
            resume = self.story.resume_state or GameState.OVERWORLD
            self.story = None
            self.state = resume
            return

    def _start_new_run(self, ng_plus: bool = False) -> None:
        """Initialize a new game run."""
        start_pos = Vector2(config.WORLD_WIDTH // 2, config.WORLD_HEIGHT // 2)
        self.player = Player(start_pos)
        self._apply_permanent_bonuses()
        if ng_plus:
            self.player.ng_mult = {
                "damage": self.ng_plus.get_multiplier("damage"),
                "health": self.ng_plus.get_multiplier("health"),
                "speed": self.ng_plus.get_multiplier("speed"),
            }
            self.player._update_stats()
            self.player.hp = self.player.max_hp
        self.player.skill_points += int(self.permanent.get_flat("start_sp"))
        self.maps_cleared = 0
        self.run_shards_earned = 0
        self._seen_acts = {0}
        self.economy.essence = int(self.permanent.get_flat("start_essence"))
        self.economy.reset_run_bonuses()
        self.overworld = OverworldMap(act_index=0)
        self.overworld_selected = 0
        opening = build_pilgrimage_pages() + build_act_descent_pages(0)
        self._start_story(opening, GameState.OVERWORLD)

    def _essence_multiplier(self) -> float:
        """Combined essence gain multiplier for the current run."""
        if not self.player:
            return 1.0
        return (
            self.player.artifacts.get_multiplier("essence")
            * self.player.perm_bonuses.get("essence", 1.0)
            * self.player.run_modifiers.get("essence_mult", 1.0)
        )

    def _xp_multiplier(self) -> float:
        """Combined XP gain multiplier for the current run."""
        if not self.player:
            return 1.0
        diff = self._diff_mult()
        return (
            diff["xp"]
            * self.player.perm_bonuses.get("xp", 1.0)
            * (1.0 + self.economy.run_xp_boost)
            * self.player.run_modifiers.get("xp_mult", 1.0)
        )

    def _prune_entities(self) -> None:
        """Remove inactive entities to prevent unbounded list growth."""
        self.projectiles = [p for p in self.projectiles if p.active]
        self.creatures = [c for c in self.creatures if c.active]
        self.bosses = [b for b in self.bosses if b.active]
        self.xp_orbs = [o for o in self.xp_orbs if o.active]

    def _load_encounter(self, node) -> None:
        """Load combat encounter for an overworld node."""
        if not self.overworld or not self.player:
            return
        seed = random.randint(0, 999999)
        act = self.overworld.act_index
        self.map_gen.load_map(act, seed)
        params = self.overworld.get_encounter_params(node)
        self.current_node_params = params
        diff = self._diff_mult()
        diff = dict(diff)
        diff["hp"] = diff["hp"] * params["hp_mult"]
        if params.get("elite"):
            diff["elite_chance"] = max(diff.get("elite_chance", 0), 0.3)

        creature_count = min(params["creatures"], config.MAX_CREATURES)
        self.creatures = self.map_gen.spawn_encounter_creatures(
            creature_count, diff, seed, elite=params.get("elite", False),
        )

        self.bosses = []
        for i in range(params.get("bosses", 0)):
            pos = Vector2(random.randint(400, config.WORLD_WIDTH - 400),
                          random.randint(400, config.WORLD_HEIGHT - 400))
            self.bosses.append(Boss(pos, act, diff, slot=i))
        for _ in range(params.get("minibosses", 0)):
            pos = Vector2(random.randint(300, config.WORLD_WIDTH - 300),
                          random.randint(300, config.WORLD_HEIGHT - 300))
            self.bosses.append(Boss(pos, act, diff, miniboss=True))

        self.projectiles.clear()
        self.xp_orbs.clear()
        self.hazards.generate_for_map(self.map_gen.hazard_types, count=2 + act, seed=seed)
        self.player.pos.set(config.WORLD_WIDTH // 2, config.WORLD_HEIGHT // 2)
        self.audio.play_act_music(act)
        if node.node_type == NodeType.BOSS:
            self.audio.play("boss_spawn")
            pages = build_boss_intro_pages(act, self.ng_plus.ng_plus_level, miniboss=False)
            self._start_story(pages, GameState.PLAYING)
        elif node.node_type == NodeType.MINIBOSS:
            self.audio.play("boss_spawn", 0.8)
            pages = build_boss_intro_pages(act, self.ng_plus.ng_plus_level, miniboss=True)
            self._start_story(pages, GameState.PLAYING)
        else:
            label = node.label
            if node.is_elite_marked:
                label = f"ELITE {label}"
            self.hud.show_notification(f"Entering: {label}", 2.0)
            self.state = GameState.PLAYING

    def _add_screen_shake(self, intensity: float) -> None:
        """Trigger screen shake."""
        self.shake_intensity = max(self.shake_intensity, intensity)

    def _update_shake(self, dt: float) -> None:
        """Update screen shake."""
        if self.shake_intensity > 0.1:
            self.shake.x = random.uniform(-self.shake_intensity, self.shake_intensity)
            self.shake.y = random.uniform(-self.shake_intensity, self.shake_intensity)
            self.shake_intensity *= config.SCREEN_SHAKE_DECAY
        else:
            self.shake.set(0, 0)
            self.shake_intensity = 0

    def run(self) -> None:
        """Main game loop."""
        running = True
        while running:
            dt = self.clock.tick(config.FPS) / 1000.0
            self.fps = self.clock.get_fps()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                self._handle_event(event)

            self._update(dt)
            self._draw()
            pygame.display.flip()

        self._save_game()
        pygame.quit()

    def _handle_event(self, event: pygame.event.Event) -> None:
        """Route events based on game state."""
        if event.type == pygame.KEYDOWN:
            if self.state == GameState.MAIN_MENU:
                self._handle_main_menu_key(event.key)
            elif self.state == GameState.STORY:
                if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e):
                    self._advance_story()
            elif self.state == GameState.PLAYING:
                self._handle_playing_key(event.key)
            elif self.state == GameState.PAUSED:
                self._handle_pause_key(event.key)
            elif self.state == GameState.SKILLS:
                self._handle_skills_key(event.key)
            elif self.state == GameState.SHOP:
                self._handle_shop_key(event.key)
            elif self.state == GameState.GAME_OVER:
                self._handle_game_over_key(event.key)
            elif self.state == GameState.VICTORY:
                self._handle_victory_key(event.key)
            elif self.state == GameState.OPTIONS:
                self._handle_options_key(event.key)
            elif self.state == GameState.HELP:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    self.state = GameState.MAIN_MENU
            elif self.state == GameState.OVERWORLD:
                self._handle_overworld_key(event.key)
            elif self.state == GameState.REST:
                if self._is_menu_select(event.key) or event.key == pygame.K_ESCAPE:
                    self._finish_non_combat_node()
            elif self.state == GameState.EVENT:
                self._handle_event_key(event.key)
            elif self.state == GameState.BLACKSMITH:
                self._handle_blacksmith_key(event.key)
            elif self.state == GameState.META_SHOP:
                self._handle_meta_key(event.key)
            elif self.state == GameState.ARCHIVE:
                self._handle_archive_key(event.key)
            elif self.state == GameState.CORE_CHOICE:
                self._handle_core_choice_key(event.key)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.state == GameState.STORY:
                    self._advance_story()
                elif self.state == GameState.OVERWORLD:
                    self._handle_overworld_click(event.pos)
                elif self.state == GameState.PLAYING and self.player:
                    world_pos = self._screen_to_world(event.pos)
                    self.player.shoot(world_pos, self.projectiles)
                elif self.state == GameState.ARCHIVE:
                    self._handle_archive_click(event.pos)
                elif self.state == GameState.CORE_CHOICE:
                    self._handle_menu_click(event.pos)
                else:
                    self._handle_menu_click(event.pos)
            elif event.button == 3 and self.state == GameState.PLAYING and self.player:
                keys = pygame.key.get_pressed()
                direction = Vector2()
                if keys[pygame.K_w] or keys[pygame.K_UP]:
                    direction.y -= 1
                if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                    direction.y += 1
                if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                    direction.x -= 1
                if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                    direction.x += 1
                if self.player.dash_cooldown <= 0:
                    self.audio.play("dash")
                self.player.dash(direction)

        if event.type == pygame.MOUSEMOTION:
            self._handle_menu_hover(event.pos)

    @staticmethod
    def _is_menu_up(key: int) -> bool:
        """Check if key navigates menu up."""
        return key in (pygame.K_UP, pygame.K_w)

    @staticmethod
    def _is_menu_down(key: int) -> bool:
        """Check if key navigates menu down."""
        return key in (pygame.K_DOWN, pygame.K_s)

    @staticmethod
    def _is_menu_left(key: int) -> bool:
        """Check if key navigates menu left."""
        return key in (pygame.K_LEFT, pygame.K_a)

    @staticmethod
    def _is_menu_right(key: int) -> bool:
        """Check if key navigates menu right."""
        return key in (pygame.K_RIGHT, pygame.K_d)

    @staticmethod
    def _is_menu_select(key: int) -> bool:
        """Check if key confirms menu selection."""
        return key in (pygame.K_RETURN, pygame.K_SPACE)

    def _handle_menu_hover(self, pos: tuple) -> None:
        """Update menu selection on mouse hover."""
        menu_states = {
            GameState.MAIN_MENU: "menu_selected",
            GameState.PAUSED: "pause_selected",
            GameState.OPTIONS: "options_selected",
            GameState.GAME_OVER: "game_over_selected",
            GameState.VICTORY: "victory_selected",
            GameState.CORE_CHOICE: "core_choice_selected",
            GameState.SHOP: "shop_selected",
        }
        if self.state not in menu_states:
            return
        if self.state == GameState.SHOP:
            idx = self.hud.hit_test_shop(pos)
        else:
            idx = self.menu.hit_test(pos)
        if idx is not None:
            setattr(self, menu_states[self.state], idx)

    def _handle_menu_click(self, pos: tuple) -> None:
        """Handle mouse click on menu items."""
        if self.state == GameState.SHOP:
            idx = self.hud.hit_test_shop(pos)
        else:
            idx = self.menu.hit_test(pos)
        if idx is None:
            return

        if self.state == GameState.MAIN_MENU:
            self.menu_selected = idx
            self._confirm_main_menu()
        elif self.state == GameState.PAUSED:
            self.pause_selected = idx
            self._confirm_pause_menu()
        elif self.state == GameState.OPTIONS:
            self.options_selected = idx
            self._confirm_options_menu()
        elif self.state == GameState.GAME_OVER:
            self.game_over_selected = idx
            self._confirm_game_over_menu()
        elif self.state == GameState.VICTORY:
            self.victory_selected = idx
            self._confirm_victory_menu()
        elif self.state == GameState.CORE_CHOICE:
            self.core_choice_selected = idx
            self._confirm_core_choice()
        elif self.state == GameState.SHOP:
            self.shop_selected = idx
            if idx < len(SHOP_ITEMS):
                self._purchase_shop_item(SHOP_ITEMS[idx]["id"])
            else:
                self._leave_shop()

    def _confirm_main_menu(self) -> None:
        """Execute main menu selection."""
        self.audio.play("ui_confirm")
        if self.menu_selected == 0:
            self._start_new_run()
        elif self.menu_selected == 1:
            self.state = GameState.META_SHOP
            self.meta_selected = 0
            self.meta_tab = 0
        elif self.menu_selected == 2:
            self.state = GameState.ARCHIVE
            self.archive_tab = 0
            self.archive_selected = 0
        elif self.menu_selected == 3:
            self.state = GameState.OPTIONS
            self.options_selected = 0
        elif self.menu_selected == 4:
            self.state = GameState.HELP
        elif self.menu_selected == 5:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _confirm_pause_menu(self) -> None:
        """Execute pause menu selection."""
        self.audio.play("ui_confirm")
        if self.pause_selected == 0:
            self.state = GameState.PLAYING
        elif self.pause_selected == 1:
            self._start_new_run()
        elif self.pause_selected == 2:
            self.audio.play_menu_music()
            self.state = GameState.MAIN_MENU

    def _confirm_options_menu(self) -> None:
        """Execute options menu selection."""
        if self.options_selected == 4:
            self.audio.play("ui_confirm")
            self.state = GameState.MAIN_MENU

    def _confirm_game_over_menu(self) -> None:
        """Execute game over menu selection."""
        if self.game_over_selected == 0:
            self._start_new_run()
        else:
            self.state = GameState.MAIN_MENU

    def _confirm_victory_menu(self) -> None:
        """Execute victory menu selection."""
        if self.victory_selected == 0:
            self._start_new_run(ng_plus=True)
        else:
            self.state = GameState.MAIN_MENU

    def _core_choice_count(self) -> int:
        """Number of available Core endings."""
        return 3 if self.permanent.broker_ending_available() else 2

    def _confirm_core_choice(self) -> None:
        """Resolve the final Core ending choice."""
        endings = ["reopen", "merge"]
        if self.permanent.broker_ending_available():
            endings.append("broker")
        idx = max(0, min(self.core_choice_selected, len(endings) - 1))
        self._trigger_victory(endings[idx])

    def _handle_core_choice_key(self, key: int) -> None:
        """Core ending choice input."""
        n = self._core_choice_count()
        if self._is_menu_up(key):
            self.core_choice_selected = (self.core_choice_selected - 1) % n
        elif self._is_menu_down(key):
            self.core_choice_selected = (self.core_choice_selected + 1) % n
        elif self._is_menu_select(key):
            self._confirm_core_choice()

    def _handle_main_menu_key(self, key: int) -> None:
        """Main menu input."""
        items = 6
        if self._is_menu_up(key):
            self.menu_selected = (self.menu_selected - 1) % items
        elif self._is_menu_down(key):
            self.menu_selected = (self.menu_selected + 1) % items
        elif self._is_menu_left(key):
            diffs = list(Difficulty)
            idx = diffs.index(self.difficulty)
            self.difficulty = diffs[(idx - 1) % len(diffs)]
        elif self._is_menu_right(key):
            diffs = list(Difficulty)
            idx = diffs.index(self.difficulty)
            self.difficulty = diffs[(idx + 1) % len(diffs)]
        elif self._is_menu_select(key):
            self._confirm_main_menu()

    def _handle_archive_key(self, key: int) -> None:
        """Archive / codex navigation."""
        entries = archive_entries_for_tab(
            self.archive_tab,
            self.permanent.unlocked_wardens,
            self.permanent.unlocked_artifacts,
            self.permanent.endings_seen,
        )
        if key == pygame.K_ESCAPE:
            self.state = GameState.MAIN_MENU
        elif key == pygame.K_TAB:
            self.archive_tab = (self.archive_tab + 1) % len(ARCHIVE_TABS)
            self.archive_selected = 0
        elif self._is_menu_left(key):
            self.archive_tab = (self.archive_tab - 1) % len(ARCHIVE_TABS)
            self.archive_selected = 0
        elif self._is_menu_right(key):
            self.archive_tab = (self.archive_tab + 1) % len(ARCHIVE_TABS)
            self.archive_selected = 0
        elif entries and self._is_menu_up(key):
            self.archive_selected = (self.archive_selected - 1) % len(entries)
        elif entries and self._is_menu_down(key):
            self.archive_selected = (self.archive_selected + 1) % len(entries)

    def _handle_archive_click(self, pos: tuple) -> None:
        """Archive mouse selection."""
        kind, idx = self.menu.archive_hit_test(pos)
        if kind == "tab" and idx is not None:
            self.archive_tab = idx
            self.archive_selected = 0
        elif kind == "entry" and idx is not None:
            self.archive_selected = idx

    def _handle_playing_key(self, key: int) -> None:
        """In-game input."""
        if key == pygame.K_p or key == pygame.K_ESCAPE:
            self.state = GameState.PAUSED
            self.pause_selected = 0
        elif key == pygame.K_TAB:
            self.state = GameState.SKILLS
        elif key == pygame.K_m:
            self.hud.show_minimap = not self.hud.show_minimap
        elif key == pygame.K_F3:
            self.hud.show_fps = not self.hud.show_fps
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6,
                     pygame.K_7, pygame.K_8, pygame.K_9):
            if self.player:
                idx = key - pygame.K_1
                if idx < len(SKILL_ORDER):
                    self._try_upgrade_skill(SKILL_ORDER[idx])

    def _handle_pause_key(self, key: int) -> None:
        """Pause menu input."""
        if self._is_menu_up(key):
            self.pause_selected = (self.pause_selected - 1) % 3
        elif self._is_menu_down(key):
            self.pause_selected = (self.pause_selected + 1) % 3
        elif self._is_menu_select(key):
            self._confirm_pause_menu()
        elif key == pygame.K_p or key == pygame.K_ESCAPE:
            self.state = GameState.PLAYING

    def _handle_skills_key(self, key: int) -> None:
        """Skills menu input."""
        if key == pygame.K_TAB or key == pygame.K_ESCAPE:
            self.state = GameState.PLAYING
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6,
                     pygame.K_7, pygame.K_8, pygame.K_9):
            idx = key - pygame.K_1
            if idx < len(SKILL_ORDER):
                self._try_upgrade_skill(SKILL_ORDER[idx])

    def _try_upgrade_skill(self, skill: str) -> None:
        """Attempt to upgrade a skill."""
        if not self.player:
            return
        if self.player.skills.can_upgrade(skill, self.player.skill_points):
            cost = self.player.skills.upgrade(skill)
            self.player.skill_points -= cost
            self.player._update_stats()
            evo = self.player.evolution.check_evolution(self.player.skills)
            if evo:
                self.hud.show_notification(evo, 3.0)

    def _handle_shop_key(self, key: int) -> None:
        """Shop input."""
        total_items = len(SHOP_ITEMS) + 1  # +1 for Continue
        if self._is_menu_up(key):
            self.shop_selected = (self.shop_selected - 1) % total_items
        elif self._is_menu_down(key):
            self.shop_selected = (self.shop_selected + 1) % total_items
        elif key == pygame.K_SPACE:
            if self.shop_selected < len(SHOP_ITEMS):
                self._purchase_shop_item(SHOP_ITEMS[self.shop_selected]["id"])
            else:
                self._leave_shop()
        elif key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self._leave_shop()

    def _leave_shop(self) -> None:
        """Exit shop and return to overworld."""
        self._finish_non_combat_node()

    def _purchase_shop_item(self, item_id: str) -> None:
        """Buy item from shop."""
        if not self.player:
            return
        item = self.economy.purchase(item_id)
        if not item:
            return
        if item["type"] == "consumable":
            self.player.heal(25)
            self.hud.show_notification("Healed 25 HP!")
        elif item["type"] == "skill_point":
            self.player.skill_points += 1
            self.hud.show_notification("+1 Skill Point!")
        elif item["type"] == "artifact":
            art_id = ArtifactManager.random_drop()
            art = self.player.artifacts.add(art_id)
            if art:
                self._unlock_artifact_archive(art_id)
                self.hud.show_notification(f"Got: {art['name']}!")
                self.player._update_stats()
        elif item["type"] == "max_health":
            self.player.shop_max_hp_bonus += 20
            self.player._update_stats()
            self.hud.show_notification("+20 Max HP!")
        elif item["type"] == "damage_boost":
            self.economy.run_damage_boost += 0.1
            self.hud.show_notification("+10% Damage!")
        elif item["type"] == "essence_cache":
            self.economy.add_essence(30, self._essence_multiplier())
            self.hud.show_notification("+30 Essence!")
        elif item["type"] == "speed_boost":
            self.economy.run_speed_boost += 0.12
            self.hud.show_notification("+12% Speed!")
        elif item["type"] == "xp_boost":
            self.economy.run_xp_boost += 0.20
            self.hud.show_notification("+20% XP!")
        elif item["type"] == "magnet_boost":
            self.economy.run_magnet_flat += 40
            self.player._update_stats()
            self.hud.show_notification("+40 Magnet Radius!")
        elif item["type"] == "size_boost":
            self.economy.run_size_boost += 0.12
            self.player.shop_size_boost = self.economy.run_size_boost
            self.player._update_stats()
            self.hud.show_notification("+12% Size!")
        elif item["type"] == "shield":
            self.player.has_shield = True
            self.hud.show_notification("Shield acquired!")
        elif item["type"] == "cleanse":
            self.player.run_modifiers["damage_taken_mult"] = 1.0
            self.player.run_modifiers["speed_mult"] = min(1.0, self.player.run_modifiers["speed_mult"] / 0.88)
            self.player.run_modifiers["hp_mult"] = min(1.0, self.player.run_modifiers["hp_mult"] / 0.88)
            self.player.run_modifiers["regen_mult"] = 1.0
            self.player._update_stats()
            self.hud.show_notification("Curses cleansed!")
        elif item["type"] == "pierce_boost":
            self.economy.run_piercing = True
            self.hud.show_notification("Piercing shots enabled!")

    def _handle_game_over_key(self, key: int) -> None:
        """Game over input."""
        if self._is_menu_up(key):
            self.game_over_selected = (self.game_over_selected - 1) % 2
        elif self._is_menu_down(key):
            self.game_over_selected = (self.game_over_selected + 1) % 2
        elif self._is_menu_select(key):
            self._confirm_game_over_menu()

    def _handle_victory_key(self, key: int) -> None:
        """Victory screen input."""
        if self._is_menu_up(key):
            self.victory_selected = (self.victory_selected - 1) % 2
        elif self._is_menu_down(key):
            self.victory_selected = (self.victory_selected + 1) % 2
        elif self._is_menu_select(key):
            self._confirm_victory_menu()

    def _handle_overworld_key(self, key: int) -> None:
        """Overworld map navigation."""
        if not self.overworld:
            return
        available = self.overworld.get_available_nodes()
        if not available:
            return
        available.sort(key=lambda n: (n.layer, n.col))
        if self._is_menu_left(key) or self._is_menu_up(key):
            self.overworld_selected = (self.overworld_selected - 1) % len(available)
        elif self._is_menu_right(key) or self._is_menu_down(key):
            self.overworld_selected = (self.overworld_selected + 1) % len(available)
        elif self._is_menu_select(key):
            node_id = available[self.overworld_selected % len(available)].id
            self._enter_node(node_id)

    def _handle_overworld_click(self, pos: tuple) -> None:
        """Click node on overworld map."""
        if not self.overworld:
            return
        node_id = self.overworld_renderer.hit_test(pos)
        if node_id:
            node = self.overworld.nodes.get(node_id)
            if node and node.available:
                self._enter_node(node_id)

    def _enter_node(self, node_id: str) -> None:
        """Travel to and activate an overworld node."""
        if not self.overworld or not self.player:
            return
        node = self.overworld.select_node(node_id)
        if not node:
            return

        if node.node_type in (NodeType.FIGHT, NodeType.ELITE, NodeType.MINIBOSS, NodeType.BOSS):
            self._load_encounter(node)
            # Boss/miniboss set STORY themselves; fights go to PLAYING.
            if self.state != GameState.STORY:
                self.state = GameState.PLAYING
        elif node.node_type == NodeType.REST:
            self.player.heal(self.player.max_hp * 0.4)
            self.hud.show_notification("The membrane folds. You heal 40% HP.", 2.0)
            self.state = GameState.REST
        elif node.node_type == NodeType.SHOP:
            self.shop_selected = 0
            self.state = GameState.SHOP
        elif node.node_type == NodeType.EVENT:
            self.event_manager.roll_event(
                act_index=self.overworld.act_index,
                ng_plus_level=self.ng_plus.ng_plus_level,
                total_runs=self.ng_plus.total_runs,
            )
            self.event_choice = 0
            self.state = GameState.EVENT
        elif node.node_type == NodeType.BLACKSMITH:
            self.blacksmith_selected = 0
            self.state = GameState.BLACKSMITH

    def _finish_non_combat_node(self) -> None:
        """Complete a non-combat node and return to overworld."""
        self._complete_current_node()

    def _complete_current_node(self) -> None:
        """Mark node done, award rewards, return to overworld or advance act."""
        if not self.overworld or not self.player:
            return
        node = self.overworld.complete_current_node()
        if not node:
            return

        params = self.overworld.get_encounter_params(node)
        non_combat_shards = {
            NodeType.REST: 1, NodeType.SHOP: 1,
            NodeType.EVENT: 3, NodeType.BLACKSMITH: 3,
        }
        shard_reward = non_combat_shards.get(node.node_type, params.get("shard_reward", 3))
        self._award_shards(shard_reward)
        self.hud.show_notification(f"+{shard_reward} shards", 2.0)

        if node.node_type == NodeType.BOSS and self.overworld.is_boss_defeated():
            self.maps_cleared += 1
            bonus = 15 + self.maps_cleared * 5
            self.economy.add_essence(bonus, self._essence_multiplier())
            self._award_shards(15)
            self.hud.show_notification(f"Layer breached! +{bonus} essence, +15 shards", 3.0)

            if self.overworld.act_index >= len(config.MAP_THEMES) - 1:
                self.permanent.add_shards(self.run_shards_earned + 50)
                self._trigger_core_choice()
                return
            next_act = self.overworld.act_index + 1
            self.overworld = OverworldMap(act_index=next_act)
            self.overworld_selected = 0
            if next_act not in self._seen_acts:
                self._seen_acts.add(next_act)
                self._start_story(build_act_descent_pages(next_act), GameState.OVERWORLD)
                return
            next_lore = get_act_lore(next_act)
            self.hud.show_notification(f"Descended into {next_lore['lore_name']}", 3.0)

        self.state = GameState.OVERWORLD
        self.overworld_selected = 0

    def _handle_event_key(self, key: int) -> None:
        """Event choice input."""
        event = self.event_manager.current_event
        if not event or not self.player:
            self._finish_non_combat_node()
            return
        choices = event["choices"]
        if self._is_menu_left(key) or self._is_menu_up(key):
            self.event_choice = (self.event_choice - 1) % len(choices)
        elif self._is_menu_right(key) or self._is_menu_down(key):
            self.event_choice = (self.event_choice + 1) % len(choices)
        elif self._is_menu_select(key):
            choice = choices[self.event_choice]
            before = set(self.player.artifacts.collected)
            boons, curses = self.event_manager.apply_choice(choice, self.player, self.player.artifacts)
            for art_id in set(self.player.artifacts.collected) - before:
                self._unlock_artifact_archive(art_id)
            for msg in boons + curses:
                self.hud.show_notification(msg, 3.0)
            self._finish_non_combat_node()

    def _handle_blacksmith_key(self, key: int) -> None:
        """Blacksmith artifact upgrade."""
        if not self.player:
            self._finish_non_combat_node()
            return
        arts = self.player.artifacts.collected
        if not arts:
            self.hud.show_notification("No artifacts to upgrade!", 2.0)
            if self._is_menu_select(key) or key == pygame.K_ESCAPE:
                self._finish_non_combat_node()
            return
        if self._is_menu_up(key):
            self.blacksmith_selected = (self.blacksmith_selected - 1) % len(arts)
        elif self._is_menu_down(key):
            self.blacksmith_selected = (self.blacksmith_selected + 1) % len(arts)
        elif self._is_menu_select(key):
            art_id = arts[self.blacksmith_selected]
            if self.player.artifacts.upgrade_artifact(art_id):
                art = ARTIFACT_DEFINITIONS.get(art_id)
                level = self.player.artifacts.get_upgrade_level(art_id)
                if art:
                    self.hud.show_notification(f"Upgraded {art['name']} to +{level * 10}%!")
                self.player._update_stats()
            else:
                self.hud.show_notification("Max upgrade level!", 2.0)
        elif key == pygame.K_ESCAPE:
            self._finish_non_combat_node()

    def _handle_meta_key(self, key: int) -> None:
        """Permanent upgrades / skins shop."""
        if key == pygame.K_TAB:
            self.meta_tab = 1 - self.meta_tab
            self.meta_selected = 0
        elif key == pygame.K_ESCAPE:
            self.state = GameState.MAIN_MENU
        elif self.meta_tab == 0:
            items = PERMANENT_UPGRADES
            if self._is_menu_up(key):
                self.meta_selected = max(0, self.meta_selected - 1)
            elif self._is_menu_down(key):
                self.meta_selected = min(len(items) - 1, self.meta_selected + 1)
            elif self._is_menu_select(key):
                upgrade = items[self.meta_selected]
                if self.permanent.purchase_upgrade(upgrade["id"]):
                    self.hud.show_notification(f"Purchased: {upgrade['name']}!", 2.0)
                    self._save_game()
                else:
                    reason = self.permanent.get_purchase_failure_reason(upgrade["id"])
                    self.hud.show_notification(reason, 2.0)
        else:
            items = SKINS
            if self._is_menu_up(key):
                self.meta_selected = (self.meta_selected - 1) % len(items)
            elif self._is_menu_down(key):
                self.meta_selected = (self.meta_selected + 1) % len(items)
            elif self._is_menu_select(key):
                skin = items[self.meta_selected]
                if skin["id"] in self.permanent.unlocked_skins:
                    self.permanent.equip_skin(skin["id"])
                    self.hud.show_notification(f"Equipped: {skin['name']}", 2.0)
                elif self.permanent.purchase_skin(skin["id"]):
                    self.permanent.equip_skin(skin["id"])
                    self.hud.show_notification(f"Unlocked: {skin['name']}!", 2.0)
                    self._save_game()
                else:
                    self.hud.show_notification(
                        self.permanent.get_skin_lock_reason(skin["id"]), 2.5,
                    )

    def _handle_options_key(self, key: int) -> None:
        """Options menu input."""
        if self._is_menu_up(key):
            self.options_selected = (self.options_selected - 1) % 5
            self.audio.play("ui_select", 0.6)
        elif self._is_menu_down(key):
            self.options_selected = (self.options_selected + 1) % 5
            self.audio.play("ui_select", 0.6)
        elif self._is_menu_left(key) or self._is_menu_right(key):
            if self.options_selected == 0:
                diffs = list(Difficulty)
                idx = diffs.index(self.difficulty)
                delta = 1 if self._is_menu_right(key) else -1
                self.difficulty = diffs[(idx + delta) % len(diffs)]
                self.audio.play("ui_select")
            elif self.options_selected == 1:
                self.hud.show_fps = not self.hud.show_fps
                self.audio.play("ui_select")
            elif self.options_selected == 2:
                self.hud.show_minimap = not self.hud.show_minimap
                self.audio.play("ui_select")
            elif self.options_selected == 3:
                enabled = self.audio.toggle()
                self.hud.show_notification(f"Sound: {'ON' if enabled else 'OFF'}", 1.5)
                if enabled:
                    self.audio.play_menu_music()
                    self.audio.play("ui_confirm")
        elif self._is_menu_select(key):
            self._confirm_options_menu()
        elif key == pygame.K_ESCAPE:
            self.state = GameState.MAIN_MENU

    def _screen_to_world(self, screen_pos: tuple) -> Vector2:
        """Convert screen coordinates to world coordinates."""
        if not self.player:
            return Vector2()
        return Vector2(
            screen_pos[0] + self.camera.x - config.SCREEN_WIDTH // 2 + self.shake.x,
            screen_pos[1] + self.camera.y - config.SCREEN_HEIGHT // 2 + self.shake.y,
        )

    def _update(self, dt: float) -> None:
        """Update game logic."""
        self.hud.update(dt)
        self._update_shake(dt)

        if self.state == GameState.STORY and self.story:
            self.cinematic.update(self.story, dt)
        elif self.state == GameState.PLAYING:
            self._update_playing(dt)
            self._update_ambient(dt)
        elif self.state == GameState.SKILLS:
            pass  # Paused gameplay

    def _update_ambient(self, dt: float) -> None:
        """Emit soft theme-colored ambient motes while exploring."""
        self._ambient_timer -= dt
        if self._ambient_timer > 0 or not self.player:
            return
        self._ambient_timer = 0.35
        theme = self.map_gen.theme
        accent = theme.get("accent", config.COLOR_PLAYER)
        for _ in range(2):
            offset = Vector2(random.uniform(-400, 400), random.uniform(-300, 300))
            self.particles.emit(
                self.player.pos + offset, 1, accent,
                speed_range=(5, 25), size_range=(1.5, 3.5),
                lifetime=1.8, gravity=False,
            )
    def _update_playing(self, dt: float) -> None:
        """Update active gameplay."""
        if not self.player:
            return

        if self._shoot_sound_cd > 0:
            self._shoot_sound_cd -= dt

        keys = pygame.key.get_pressed()
        direction = self.player.handle_input(keys, dt)

        hazard_effects = self.hazards.get_player_effects(self.player.pos, dt)
        speed_mult = hazard_effects["speed_mult"] * (1.0 + self.economy.run_speed_boost)

        slow_radius = 200
        if self.player.artifacts.has("time_dilation"):
            slow_factor = self.player.artifacts.get_slow_radius()
            for creature in self.creatures:
                if creature.active and self.player.pos.distance_to(creature.pos) < slow_radius:
                    creature.slow_factor = 1.0 - slow_factor
                else:
                    creature.slow_factor = 1.0
            for boss in self.bosses:
                if boss.active and self.player.pos.distance_to(boss.pos) < slow_radius:
                    boss.slow_factor = 1.0 - slow_factor
                else:
                    boss.slow_factor = 1.0

        self.player.move(direction, dt, speed_mult)
        self.player.update(dt)

        if self.player.artifacts.has("dash_trail") and self.player.dash_duration > 0:
            trail_radius = self.player.size * 1.2
            trail_damage = self.player.damage * 0.4 * dt * 10
            for creature in self.creatures:
                if creature.active and self.player.pos.distance_to(creature.pos) < trail_radius + creature.radius:
                    creature.take_damage(
                        trail_damage, self.player.artifacts.get_ignore_defense(),
                        hit_from=self.player.pos,
                    )

        if self._boss_touch_cooldown > 0:
            self._boss_touch_cooldown -= dt

        if hazard_effects["damage"] > 0:
            if self.player.take_damage(hazard_effects["damage"]):
                self.audio.play("hurt")
                self._trigger_game_over()
                return

        # Hold to shoot
        mouse_pressed = pygame.mouse.get_pressed()
        if mouse_pressed[0]:
            before = len(self.projectiles)
            mouse_pos = pygame.mouse.get_pos()
            world_pos = self._screen_to_world(mouse_pos)
            self.player.shoot(world_pos, self.projectiles)
            if len(self.projectiles) > before and self._shoot_sound_cd <= 0:
                self.audio.play("shoot", 0.55)
                self._shoot_sound_cd = 0.08

        # Update entities
        for creature in self.creatures:
            if creature.active:
                creature.update(dt, self.player.pos, self.player.size, self.projectiles)

        for boss in self.bosses:
            if boss.active:
                boss.update(dt, self.player.pos, self.projectiles)
                if boss.consume_phase_announce():
                    self.audio.play("boss_phase")
                    label = "FINAL PHASE!" if boss.phase >= 3 else f"{boss.name} — PHASE {boss.phase}!"
                    self.hud.show_notification(label, 2.5)
                    self._add_screen_shake(10)

        self._process_explosions()
        self._update_projectiles(dt)
        self._update_collisions()
        self._update_xp_orbs(dt)
        self.hazards.update(dt)
        self.particles.update(dt)

        if self.player.vel.length() > 50:
            self.particles.emit_trail(self.player.pos, self.player.vel, config.COLOR_PLAYER)

        self.camera_target.set(self.player.pos.x, self.player.pos.y)
        self.camera.lerp(self.camera_target, config.CAMERA_SMOOTH)

        alive_bosses = sum(1 for b in self.bosses if b.active)
        alive_creatures = sum(1 for c in self.creatures if c.active)
        if alive_bosses == 0 and alive_creatures == 0:
            self._complete_level()

        self._prune_entities()

    def _process_explosions(self) -> None:
        """Resolve bomber / death explosions."""
        if not self.player:
            return
        for creature in list(self.creatures):
            if not creature.pending_explosion:
                continue
            creature.pending_explosion = False
            was_active_kill = creature.hp <= 0
            creature.active = False
            self.audio.play("explode")
            self.particles.emit_explosion(creature.pos, (255, 120, 40), 28)
            self._add_screen_shake(8)
            radius = creature.explosion_radius
            damage = creature.explosion_damage
            if was_active_kill and not creature.kills_awarded:
                creature.kills_awarded = True
                self.player.kills += 1
                xp = int(creature.xp_value * self._xp_multiplier() * 0.75)
                self.player.add_xp(xp)
                self.economy.add_essence(int(creature.xp_value * 0.04), self._essence_multiplier())
            if self.player.pos.distance_to(creature.pos) < radius + self.player.radius:
                if self.player.take_damage(damage):
                    self.audio.play("hurt")
                    self._trigger_game_over()
                    return
            for other in self.creatures:
                if other.active and other is not creature:
                    if other.pos.distance_to(creature.pos) < radius + other.radius:
                        if other.take_damage(damage * 0.5, hit_from=creature.pos):
                            self._on_creature_killed(other)

    def _update_projectiles(self, dt: float) -> None:
        """Update all projectiles."""
        for proj in self.projectiles:
            if proj.active:
                proj.update(dt)

        # Player hit by enemy projectiles
        if self.player:
            for proj in self.projectiles:
                if proj.active and not proj.from_player:
                    if proj.collides_with(self.player.pos, self.player.radius):
                        if self.player.take_damage(proj.damage):
                            self.audio.play("hurt")
                            self._trigger_game_over()
                        else:
                            self.audio.play("hurt", 0.7)
                        proj.active = False
                        self._add_screen_shake(5)

    def _update_collisions(self) -> None:
        """Handle all collision detection."""
        if not self.player:
            return

        ignore_def = self.player.artifacts.get_ignore_defense()
        damage_mult = 1.0 + self.economy.run_damage_boost
        pierce = self.player.artifacts.has("piercing_shots") or self.economy.run_piercing
        diff = self._diff_mult()

        # Player projectiles vs creatures
        for proj in self.projectiles:
            if not proj.active or not proj.from_player:
                continue
            proj.piercing = pierce
            hit_damage = proj.damage * damage_mult
            if random.random() < self.player.get_crit_chance():
                hit_damage *= 1.5
            for creature in self.creatures:
                if creature.active and proj.collides_with(creature.pos, creature.radius):
                    killed = creature.take_damage(hit_damage, ignore_def, hit_from=proj.pos)
                    self.particles.emit_sparkle(creature.pos, (255, 200, 100))
                    self.audio.play("hit", 0.45)
                    if killed:
                        self._on_creature_killed(creature)
                    if not proj.piercing:
                        proj.active = False
                        break

            for boss in self.bosses:
                if boss.active and proj.collides_with(boss.pos, boss.radius):
                    killed = boss.take_damage(hit_damage, ignore_def)
                    self.audio.play("boss_hit", 0.55)
                    self._add_screen_shake(3)
                    if killed:
                        self._on_boss_killed(boss)
                    if not proj.piercing:
                        proj.active = False
                        break

        # Player vs creatures (absorption / damage)
        for creature in self.creatures:
            if not creature.active:
                continue
            dist = self.player.pos.distance_to(creature.pos)
            if dist < self.player.radius + creature.radius:
                if creature.phased:
                    continue
                if self.player.size > creature.size * 1.1:
                    self.player.absorb_creature(creature.size, creature.hp)
                    self.particles.emit_explosion(creature.pos, (200, 80, 80))
                    self.audio.play("absorb")
                    if creature.ctype == CreatureType.BOMBER:
                        creature.pending_explosion = True
                    creature.active = False
                    essence_gain = int(creature.xp_value * 0.08 * diff["xp"])
                    self.economy.add_essence(essence_gain, self._essence_multiplier())
                elif creature.size > self.player.size * 1.1 or creature.ctype == CreatureType.LEECH:
                    dmg = creature.damage
                    if creature.ctype == CreatureType.LEECH:
                        dmg *= 0.35  # continuous siphon handled lightly per frame contact
                    if self.player.take_damage(dmg):
                        self.audio.play("hurt")
                        self._trigger_game_over()
                        return

        # Player vs bosses (contact damage with cooldown)
        for boss in self.bosses:
            if not boss.active:
                continue
            if self._boss_touch_cooldown <= 0 and self.player.pos.distance_to(boss.pos) < self.player.radius + boss.radius:
                if self.player.take_damage(boss.damage * 0.5):
                    self.audio.play("hurt")
                    self._trigger_game_over()
                    return
                self.audio.play("hurt", 0.6)
                self._boss_touch_cooldown = 0.6
                self._add_screen_shake(6)

        # Charger collision
        for creature in self.creatures:
            if creature.active and creature.ctype == CreatureType.CHARGER and creature.charging:
                if self.player.pos.distance_to(creature.pos) < self.player.radius + creature.radius:
                    if self.player.take_damage(creature.damage):
                        self.audio.play("hurt")
                        self._trigger_game_over()
                        return
                    self.audio.play("hurt", 0.8)
                    self._add_screen_shake(8)

    def _on_creature_killed(self, creature: Creature) -> None:
        """Handle creature death."""
        if not self.player:
            return
        if creature.kills_awarded:
            return
        creature.kills_awarded = True
        creature.active = False
        creature.hp = 0
        self.player.kills += 1

        xp_mult = self._xp_multiplier()
        if self.player.artifacts.has("xp_chain"):
            self.player.kill_streak += 1
            self.player.kill_streak_timer = 2.5
            chain_bonus = 1.0 + min(0.5, self.player.kill_streak * 0.05)
            xp_mult *= chain_bonus

        xp = int(creature.xp_value * xp_mult)
        messages = self.player.add_xp(xp)
        for msg in messages:
            self.hud.show_notification(msg, 2.0)
            if "Level" in msg or "level" in msg.lower():
                self.audio.play("levelup")
        self.audio.play("kill", 0.7)
        self.xp_orbs.append(XPOrb(creature.pos.copy(), xp))
        essence_gain = int(creature.xp_value * 0.05)
        self.economy.add_essence(essence_gain, self._essence_multiplier())
        self.particles.emit_explosion(creature.pos, (255, 150, 50))
        self._add_screen_shake(2)

        ls = self.player.get_lifesteal()
        if ls > 0:
            self.player.heal(creature.max_hp * ls)

        if self.player.artifacts.has("explosive_death"):
            self.particles.emit_explosion(creature.pos, (255, 100, 30), 30)

        if creature.ctype == CreatureType.BOMBER:
            creature.pending_explosion = True

        if creature.can_split():
            for child in creature.create_splits():
                self.creatures.append(child)

        if self.player.artifacts.has("quantum_split"):
            for angle_offset in (-0.4, 0.4):
                direction = Vector2(
                    math.cos(self.player.rotation + angle_offset),
                    math.sin(self.player.rotation + angle_offset),
                )
                speed = 500 + self.player.skills.get_level("projectile") * 30
                self.projectiles.append(
                    Projectile(creature.pos.copy(), direction, speed, self.player.damage, True,
                               self.player.artifacts.has("piercing_shots")),
                )

        if random.random() < 0.08 + self.player.perm_bonuses.get("luck", 0.0):
            art_id = ArtifactManager.random_drop()
            art = self.player.artifacts.add(art_id)
            if art:
                self._unlock_artifact_archive(art_id)
                self.hud.show_notification(f"Artifact: {art['name']}!", 3.0)
                self.player._update_stats()

    def _unlock_artifact_archive(self, artifact_id: str) -> None:
        """Record artifact lore in the Archive when first collected."""
        if self.permanent.unlock_artifact_lore(artifact_id):
            self._save_game()

    def _on_boss_killed(self, boss: Boss) -> None:
        """Handle boss death."""
        if not self.player:
            return
        boss.active = False
        boss.hp = 0
        self.player.kills += 1
        xp = int(boss.xp_value * self._xp_multiplier() * 2)
        messages = self.player.add_xp(xp)
        for msg in messages:
            self.hud.show_notification(msg, 2.0)
        self.xp_orbs.append(XPOrb(boss.pos.copy(), xp))
        essence_gain = int(boss.xp_value * 0.12)
        self.economy.add_essence(essence_gain, self._essence_multiplier())
        self.particles.emit_explosion(boss.pos, (255, 80, 80), 40)
        self.audio.play("kill")
        self.audio.play("explode", 0.8)
        self._add_screen_shake(12)

        if not boss.is_miniboss:
            frag_id = get_warden_fragment_id(boss.act_index)
            if self.permanent.unlock_warden(frag_id):
                lore = get_act_lore(boss.act_index)
                self.hud.show_notification(f"Archive: {lore['warden']} remembered", 3.5)
                self._save_game()

        if random.random() < 0.25:
            art_id = ArtifactManager.random_drop()
            art = self.player.artifacts.add(art_id)
            if art:
                self._unlock_artifact_archive(art_id)
                self.hud.show_notification(f"Boss Artifact: {art['name']}!", 3.0)
                self.player._update_stats()

    def _update_xp_orbs(self, dt: float) -> None:
        """Update XP orb collection."""
        if not self.player:
            return
        magnet = self.player.magnet_radius + self.economy.run_magnet_flat
        xp_mult = self._xp_multiplier()
        if self.player.kill_streak_timer > 0:
            self.player.kill_streak_timer -= dt
            if self.player.kill_streak_timer <= 0:
                self.player.kill_streak = 0
        for orb in self.xp_orbs:
            if orb.active:
                orb.update(dt, self.player.pos, magnet)
                if orb.collides_with(self.player.pos, self.player.radius):
                    messages = self.player.add_xp(int(orb.value * xp_mult))
                    for msg in messages:
                        self.hud.show_notification(msg, 2.0)
                        if "Level" in msg or "level" in msg.lower():
                            self.audio.play("levelup")
                    self.audio.play("pickup", 0.5)
                    orb.active = False
                    self.particles.emit_sparkle(orb.pos, config.COLOR_XP)

    def _complete_level(self) -> None:
        """Handle combat encounter completion."""
        self._complete_current_node()

    def _trigger_game_over(self) -> None:
        """Transition to game over."""
        if not self.player:
            return
        self.run_stats = {
            "level": self.player.level,
            "kills": self.player.kills,
            "maps_cleared": self.maps_cleared,
            "total_xp": self.player.total_xp,
            "essence": self.economy.essence,
            "best_layer_before": self.ng_plus.best_map_reached + 1,
        }
        self.ng_plus.complete_run(self.maps_cleared)
        self.permanent.add_shards(max(5, self.run_shards_earned // 2))
        for art_id in self.player.artifacts.collected:
            self.permanent.unlock_artifact_lore(art_id)
        self._save_game()
        self.audio.play("defeat")
        self.audio.play_menu_music()
        self.state = GameState.GAME_OVER
        self.game_over_selected = 0

    def _trigger_core_choice(self) -> None:
        """Open the final ending choice at the Core."""
        if not self.player:
            return
        for art_id in self.player.artifacts.collected:
            self.permanent.unlock_artifact_lore(art_id)
        self.core_choice_selected = 0
        self.state = GameState.CORE_CHOICE

    def _trigger_victory(self, ending: str = "reopen") -> None:
        """Transition to victory for a chosen Core ending."""
        if not self.player:
            return
        self.run_ending = ending
        self.run_stats = {
            "level": self.player.level,
            "kills": self.player.kills,
            "essence": self.economy.essence,
            "artifacts": len(self.player.artifacts.collected),
            "ending": ending,
        }
        self.permanent.record_ending(ending)
        msg = self.ng_plus.complete_run(self.maps_cleared)
        for art_id in self.player.artifacts.collected:
            self.permanent.unlock_artifact_lore(art_id)
        self._save_game()
        self.audio.play("victory")
        self.audio.play_menu_music()
        self.state = GameState.VICTORY
        self.victory_selected = 0
        self.hud.show_notification(msg, 5.0)

    def _draw(self) -> None:
        """Render current frame."""
        if self.state == GameState.MAIN_MENU:
            self.menu.draw_main_menu(self.screen, self.menu_selected, self.difficulty)
        elif self.state == GameState.STORY and self.story:
            self.cinematic.draw(self.screen, self.story)
        elif self.state == GameState.OVERWORLD and self.overworld:
            available = self.overworld.get_available_nodes()
            available.sort(key=lambda n: (n.layer, n.col))
            selected_id = None
            if available:
                selected_id = available[self.overworld_selected % len(available)].id
            self.overworld_renderer.draw(
                self.screen, self.overworld,
                self.permanent.shards, self.economy.essence,
                selected_node_id=selected_id,
            )
            if self.hud.notification_timer > 0:
                notif = self.hud.font_large.render(self.hud.notification, True, (255, 220, 100))
                self.screen.blit(notif, (config.SCREEN_WIDTH // 2 - notif.get_width() // 2, 70))
        elif self.state in (GameState.PLAYING, GameState.SKILLS, GameState.PAUSED):
            self._draw_game()
            if self.state == GameState.SKILLS:
                self.hud.draw_skills_overlay(self.screen, self.player)
            elif self.state == GameState.PAUSED:
                self.menu.draw_pause_menu(self.screen, self.pause_selected)
        elif self.state == GameState.SHOP:
            self._draw_game()
            if self.player:
                self.hud.draw_shop_overlay(self.screen, self.player, self.economy.essence, self.shop_selected)
        elif self.state == GameState.REST:
            act = self.overworld.act_index if self.overworld else 0
            journal = get_act_journal(act)
            self._draw_overlay_screen(REST_TITLE, f"{REST_SUBTITLE}\n\n{journal}")
        elif self.state == GameState.EVENT:
            self._draw_event_screen()
        elif self.state == GameState.BLACKSMITH:
            self._draw_blacksmith_screen()
        elif self.state == GameState.META_SHOP:
            self._draw_meta_screen()
        elif self.state == GameState.ARCHIVE:
            self.menu.draw_archive(
                self.screen,
                self.archive_tab,
                self.archive_selected,
                self.permanent.unlocked_wardens,
                self.permanent.unlocked_artifacts,
                self.permanent.endings_seen,
            )
        elif self.state == GameState.CORE_CHOICE:
            self.menu.draw_core_choice(
                self.screen,
                self.core_choice_selected,
                self.permanent.broker_ending_available(),
            )
        elif self.state == GameState.GAME_OVER:
            self.menu.draw_game_over(self.screen, self.run_stats, self.game_over_selected)
        elif self.state == GameState.VICTORY:
            self.menu.draw_victory(
                self.screen, self.run_stats, self.victory_selected,
                self.ng_plus.ng_plus_level, self.run_stats.get("ending", self.run_ending),
            )
        elif self.state == GameState.OPTIONS:
            self.menu.draw_options(self.screen, self.options_selected, self.difficulty,
                                   self.hud.show_fps, self.hud.show_minimap, self.audio.enabled)
        elif self.state == GameState.HELP:
            self.menu.draw_help(self.screen)

    def _draw_overlay_screen(self, title: str, subtitle: str) -> None:
        """Draw a simple full-screen overlay."""
        accent = style.ACCENT_SOFT
        if self.overworld:
            lore = get_act_lore(self.overworld.act_index)
            accent = lore.get("accent", accent)
        style.draw_ambient_bg(self.screen, accent=accent)
        font_lg = pygame.font.SysFont("segoeui", 34, bold=True)
        font_sm = pygame.font.SysFont("segoeui", 17)
        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 340, 160, 680, 420)
        style.draw_panel(self.screen, panel)
        t = font_lg.render(title, True, style.TEXT)
        self.screen.blit(t, (config.SCREEN_WIDTH // 2 - t.get_width() // 2, panel.y + 36))
        sub_y = panel.y + 100
        for paragraph in subtitle.split("\n"):
            if not paragraph.strip():
                sub_y += 12
                continue
            for line in wrap_text(paragraph, font_sm, panel.width - 80):
                s = font_sm.render(line, True, style.TEXT_DIM)
                self.screen.blit(s, (config.SCREEN_WIDTH // 2 - s.get_width() // 2, sub_y))
                sub_y += 24
            sub_y += 6
        style.draw_hint(self.screen, font_sm, "Press SPACE to continue")
    def _draw_event_screen(self) -> None:
        """Draw random event UI."""
        style.draw_ambient_bg(self.screen, seed_offset=7.0, accent=(80, 50, 110))
        event = self.event_manager.current_event
        if not event:
            return
        font_lg = pygame.font.SysFont("segoeui", 28, bold=True)
        font_sm = pygame.font.SysFont("segoeui", 16)
        panel = pygame.Rect(100, 80, config.SCREEN_WIDTH - 200, 560)
        style.draw_panel(self.screen, panel)
        title = font_lg.render(event["title"], True, style.ESSENCE)
        self.screen.blit(title, (config.SCREEN_WIDTH // 2 - title.get_width() // 2, panel.y + 28))
        desc_y = panel.y + 80
        for line in wrap_text(event["description"], font_sm, panel.width - 80):
            desc = font_sm.render(line, True, style.TEXT_DIM)
            self.screen.blit(desc, (config.SCREEN_WIDTH // 2 - desc.get_width() // 2, desc_y))
            desc_y += 22
        for i, choice in enumerate(event["choices"]):
            row = pygame.Rect(panel.x + 60, desc_y + 30 + i * 56, panel.width - 120, 48)
            if i == self.event_choice:
                style.draw_panel(self.screen, row, edge=style.SELECT, radius=8, alpha=200)
            color = style.SELECT if i == self.event_choice else style.TEXT
            text = font_sm.render(choice["label"], True, color)
            self.screen.blit(text, (row.x + 20, row.y + 14))
        style.draw_hint(self.screen, font_sm, "WASD select  ·  SPACE confirm")

    def _draw_blacksmith_screen(self) -> None:
        """Draw blacksmith upgrade UI."""
        style.draw_ambient_bg(self.screen, seed_offset=8.0, accent=(110, 70, 40))
        font_lg = pygame.font.SysFont("segoeui", 28, bold=True)
        font_sm = pygame.font.SysFont("segoeui", 16)
        panel = pygame.Rect(80, 50, config.SCREEN_WIDTH - 160, 680)
        style.draw_panel(self.screen, panel)
        title = font_lg.render(BLACKSMITH_TITLE, True, style.WARN)
        self.screen.blit(title, (config.SCREEN_WIDTH // 2 - title.get_width() // 2, panel.y + 24))
        sub_y = panel.y + 70
        for line in wrap_text(BLACKSMITH_SUBTITLE, font_sm, panel.width - 80):
            sub = font_sm.render(line, True, style.TEXT_DIM)
            self.screen.blit(sub, (config.SCREEN_WIDTH // 2 - sub.get_width() // 2, sub_y))
            sub_y += 22
        if not self.player or not self.player.artifacts.collected:
            msg = font_sm.render("No artifacts to upgrade. Press SPACE to leave.", True, style.TEXT)
            self.screen.blit(msg, (config.SCREEN_WIDTH // 2 - msg.get_width() // 2, 300))
            style.draw_hint(self.screen, font_sm, "SPACE or ESC to leave")
            return
        sub = font_sm.render("Select an artifact to upgrade (+10% effect)", True, style.TEXT_MUTED)
        self.screen.blit(sub, (config.SCREEN_WIDTH // 2 - sub.get_width() // 2, sub_y + 10))
        list_y = sub_y + 40
        for i, art_id in enumerate(self.player.artifacts.collected):
            art = ARTIFACT_DEFINITIONS.get(art_id, {})
            level = self.player.artifacts.get_upgrade_level(art_id)
            row = pygame.Rect(panel.x + 50, list_y + i * 40, panel.width - 100, 36)
            if i == self.blacksmith_selected:
                style.draw_panel(self.screen, row, edge=style.SELECT, radius=6, alpha=200)
            color = style.SELECT if i == self.blacksmith_selected else style.TEXT
            suffix = f"  (+{level * 10}%)" if level else ""
            lineage = get_artifact_lineage_name(art_id)
            text = font_sm.render(
                f"{art.get('name', art_id)}{suffix}  ·  {lineage}", True, color,
            )
            self.screen.blit(text, (row.x + 16, row.y + 8))
        if self.player.artifacts.collected:
            sel_id = self.player.artifacts.collected[self.blacksmith_selected]
            blurb = get_artifact_blurb(sel_id)
            blurb_y = list_y + len(self.player.artifacts.collected) * 40 + 24
            for line in wrap_text(blurb, font_sm, panel.width - 100):
                rendered = font_sm.render(line, True, (170, 150, 130))
                self.screen.blit(rendered, (config.SCREEN_WIDTH // 2 - rendered.get_width() // 2, blurb_y))
                blurb_y += 22
        style.draw_hint(self.screen, font_sm, "WASD select  ·  SPACE upgrade  ·  ESC leave")

    def _draw_meta_screen(self) -> None:
        """Draw permanent upgrades and skins shop."""
        style.draw_ambient_bg(self.screen, seed_offset=9.0, accent=(70, 50, 100))
        font_lg = pygame.font.SysFont("segoeui", 28, bold=True)
        font_sm = pygame.font.SysFont("segoeui", 16)
        style.draw_title_block(
            self.screen, font_lg, font_sm, "Permanent Upgrades",
            f"Shards: {self.permanent.shards}", y=24, color=style.SHARD,
        )
        panel = pygame.Rect(100, 110, config.SCREEN_WIDTH - 200, 600)
        style.draw_panel(self.screen, panel)
        tab_names = ["Upgrades", "Skins"]
        for i, name in enumerate(tab_names):
            color = style.SELECT if i == self.meta_tab else style.TEXT_MUTED
            tab_rect = pygame.Rect(panel.x + 40 + i * 130, panel.y + 16, 120, 30)
            if i == self.meta_tab:
                style.draw_panel(self.screen, tab_rect, edge=style.SELECT, radius=6, alpha=180)
            tab = font_sm.render(name, True, color)
            self.screen.blit(tab, (tab_rect.centerx - tab.get_width() // 2, tab_rect.y + 5))
        if self.meta_tab == 0:
            visible = 12
            self.meta_scroll = max(0, min(self.meta_selected - visible // 2, len(PERMANENT_UPGRADES) - visible))
            for i, upg in enumerate(PERMANENT_UPGRADES):
                if i < self.meta_scroll or i >= self.meta_scroll + visible:
                    continue
                row = i - self.meta_scroll
                level = self.permanent.upgrade_levels.get(upg["id"], 0)
                cost = self.permanent.get_upgrade_cost(upg["id"])
                yy = panel.y + 60 + row * 36
                row_rect = pygame.Rect(panel.x + 36, yy, panel.width - 72, 32)
                if i == self.meta_selected:
                    style.draw_panel(self.screen, row_rect, edge=style.SELECT, radius=6, alpha=180)
                color = style.SELECT if i == self.meta_selected else style.TEXT
                text = font_sm.render(
                    f"{upg['name']}  Lv.{level}/{upg['max_level']}  —  {cost} shards", True, color,
                )
                self.screen.blit(text, (row_rect.x + 14, row_rect.y + 6))
            if self.meta_selected < len(PERMANENT_UPGRADES):
                sel = PERMANENT_UPGRADES[self.meta_selected]
                desc = font_sm.render(sel["description"], True, style.TEXT_DIM)
                self.screen.blit(desc, (config.SCREEN_WIDTH // 2 - desc.get_width() // 2, panel.bottom - 50))
        else:
            for i, skin in enumerate(SKINS):
                owned = skin["id"] in self.permanent.unlocked_skins
                equipped = skin["id"] == self.permanent.equipped_skin
                gated = not self.permanent.skin_requirement_met(skin)
                if equipped:
                    status = "  ·  Equipped"
                elif owned:
                    status = "  ·  Owned"
                elif gated:
                    status = f"  —  {skin.get('lock_hint', 'Locked')}"
                else:
                    status = f"  —  {skin['cost']} shards"
                yy = panel.y + 60 + i * 40
                row_rect = pygame.Rect(panel.x + 36, yy, panel.width - 72, 36)
                if i == self.meta_selected:
                    style.draw_panel(self.screen, row_rect, edge=style.SELECT, radius=6, alpha=180)
                color = style.SELECT if i == self.meta_selected else (
                    style.TEXT_MUTED if gated and not owned else style.TEXT
                )
                pygame.draw.circle(self.screen, skin["color"], (row_rect.x + 22, row_rect.centery), 9)
                pygame.draw.circle(self.screen, skin["core"], (row_rect.x + 22, row_rect.centery), 4)
                text = font_sm.render(f"{skin['name']}{status}", True, color)
                self.screen.blit(text, (row_rect.x + 44, row_rect.y + 8))
            if 0 <= self.meta_selected < len(SKINS):
                lore = SKINS[self.meta_selected].get("lore", "")
                if lore:
                    desc = font_sm.render(lore, True, style.TEXT_DIM)
                    self.screen.blit(
                        desc,
                        (config.SCREEN_WIDTH // 2 - desc.get_width() // 2, panel.bottom - 50),
                    )
        style.draw_hint(
            self.screen, font_sm,
            "TAB switch  ·  WASD navigate  ·  SPACE buy/equip  ·  ESC back",
        )

    def _draw_game(self) -> None:
        """Draw gameplay scene."""
        self.map_gen.draw_background(self.screen, self.camera, self.shake)
        self.hazards.draw(self.screen, self.camera, self.shake)

        for orb in self.xp_orbs:
            if orb.active:
                orb.draw(self.screen, self.camera, self.shake)

        for creature in self.creatures:
            if creature.active:
                creature.draw(self.screen, self.camera, self.shake)

        for boss in self.bosses:
            if boss.active:
                boss.draw(self.screen, self.camera, self.shake)

        for proj in self.projectiles:
            if proj.active:
                proj.draw(self.screen, self.camera, self.shake)

        self.particles.draw(self.screen, self.camera, self.shake)

        if self.player:
            mouse = pygame.mouse.get_pos()
            look = (
                mouse[0] - (self.player.pos.x - self.camera.x + config.SCREEN_WIDTH // 2 + self.shake.x),
                mouse[1] - (self.player.pos.y - self.camera.y + config.SCREEN_HEIGHT // 2 + self.shake.y),
            )
            self.player.draw(self.screen, self.camera, self.shake, look_target=look)
            self.hud.draw(
                self.screen, self.player, self.creatures, self.bosses,
                self.xp_orbs, self.hazards, self.camera, self.fps,
                self.map_gen.map_name, self.economy.essence,
            )
