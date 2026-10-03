"""TASK-023: upgrade levels within max, non-negative bonuses, and the partial vs recovered save notice.

Follow-ups to TASK-022 (strict save types): BUG-046 (negative / inf / NaN bonuses), BUG-047 (levels above max,
unknown upgrade ids), BUG-048 (partial notice) and BUG-049 (the two mutations QA's review found nothing failing for).
Every boot test builds a real Game from a save on disk.
"""
import copy
import json
from typing import Any, Dict, List, Tuple

import pytest

from blob_evolution import config
from blob_evolution.data import lore
from blob_evolution.systems.newgameplus import NewGamePlus
from blob_evolution.systems.permanent import PERMANENT_UPGRADES, PermanentProgress
from blob_evolution.systems.savefile import INT_MAX, SaveSection

NAN, INF = float("nan"), float("inf")
BAK = config.SAVE_BACKUP_SUFFIX
MAX_LEVELS: Dict[str, int] = {u["id"]: u["max_level"] for u in PERMANENT_UPGRADES}
IDS = list(MAX_LEVELS)
BONUS_KEYS = ["damage", "health", "speed", "essence"]


def _boot(make_game, isolated_save, data: Any, capsys, raw: bytes = None):
    """Write data (or raw bytes) as the save, boot a real Game, return (game, raw, stderr)."""
    raw = raw if raw is not None else json.dumps(data, indent=2).encode()
    isolated_save.write_bytes(raw)
    capsys.readouterr()
    game = make_game()
    return game, raw, capsys.readouterr().err


def _backed_up(isolated_save, raw: bytes) -> bool:
    bak = isolated_save.parent / (isolated_save.name + BAK)
    return bak.exists() and bak.read_bytes() == raw


def _no_bak(isolated_save) -> bool:
    return not (isolated_save.parent / (isolated_save.name + BAK)).exists()


def _warned(err: str) -> bool:
    return "[save]" in err and "invalid data" in err


# --- BUG-047: SaveSection.integer_dict with limits -----------------------------------------------------

LIMITS = {"a": 5, "b": 3}
# (id, value, kept?) for key "a" with limit 5
LEVEL_CASES: List[Tuple[str, Any, bool]] = [
    ("zero", 0, True),
    ("one", 1, True),
    ("max_minus_1", 4, True),
    ("max", 5, True),
    ("max_plus_1", 6, False),
    ("minus_1", -1, False),
    ("int_max", INT_MAX, False),
    ("int_max_plus_1", INT_MAX + 1, False),
    ("fraction", 2.5, False),
    ("whole_float", 2.0, False),
    ("bool", True, False),
]


@pytest.mark.parametrize("name,value,kept", LEVEL_CASES, ids=[c[0] for c in LEVEL_CASES])
def test_integer_dict_limit_boundaries(name: str, value: Any, kept: bool) -> None:
    """At the limit and below loads quietly; above it (or not a count) is dropped, the sibling entry stays."""
    section = SaveSection({"t": {"a": value, "b": 2}})
    got = section.integer_dict("t", {}, LIMITS)
    assert got == ({"a": value, "b": 2} if kept else {"b": 2})
    assert section.valid is kept
    assert section.table_reset is False


def test_integer_dict_unknown_key_is_dropped_but_others_stay() -> None:
    """A key outside limits is dropped and flagged; known keys, even at their limit, load."""
    section = SaveSection({"t": {"a": 5, "zzz": 1, "b": 0}})
    assert section.integer_dict("t", {}, LIMITS) == {"a": 5, "b": 0}
    assert section.valid is False and section.table_reset is False


def test_integer_dict_without_limits_still_accepts_any_key_and_big_counts() -> None:
    """022's behaviour is unchanged when no limits are given."""
    section = SaveSection({"t": {"x": INT_MAX, "y": 3}})
    assert section.integer_dict("t", {}) == {"x": INT_MAX, "y": 3}
    assert section.valid is True


def test_every_real_upgrade_has_a_limit_from_the_definitions() -> None:
    """The limits come from the real upgrade table (the one get_upgrade_cost uses), all 13 of them."""
    assert len(IDS) == 13 and all(isinstance(v, int) and v >= 1 for v in MAX_LEVELS.values())
    assert MAX_LEVELS["perm_damage"] == 5 and MAX_LEVELS["perm_start_sp"] == 2


@pytest.mark.parametrize("upgrade_id", IDS)
def test_permanent_from_dict_level_boundaries(upgrade_id: str) -> None:
    """For every real upgrade: max loads, max+1 / -1 / INT_MAX / INT_MAX+1 fall back to 0."""
    top = MAX_LEVELS[upgrade_id]
    for level in (0, 1, top - 1, top):
        perm = PermanentProgress()
        assert perm.from_dict({"upgrade_levels": {upgrade_id: level}}) is True
        assert perm.upgrade_levels[upgrade_id] == level and perm.table_reset is False
    for level in (top + 1, -1, INT_MAX, INT_MAX + 1):
        perm = PermanentProgress()
        assert perm.from_dict({"upgrade_levels": {upgrade_id: level}}) is False
        assert perm.upgrade_levels[upgrade_id] == 0 and perm.table_reset is False


def test_permanent_from_dict_unknown_upgrade_id_is_dropped_not_loaded() -> None:
    """An unknown id is not added to upgrade_levels; the valid entries beside it load."""
    perm = PermanentProgress()
    ok = perm.from_dict({"upgrade_levels": {"perm_damage": 3, "perm_not_real": 1, "": 2}})
    assert ok is False
    assert "perm_not_real" not in perm.upgrade_levels and "" not in perm.upgrade_levels
    assert perm.upgrade_levels["perm_damage"] == 3
    assert set(perm.upgrade_levels) == set(IDS)


def test_permanent_from_dict_keeps_valid_entries_beside_a_bad_one() -> None:
    """Decision: only the bad entry resets (to level 0); every valid entry in the table is kept."""
    levels = {uid: MAX_LEVELS[uid] for uid in IDS}
    levels["perm_health"] = MAX_LEVELS["perm_health"] + 1
    levels["perm_unknown"] = 1
    perm = PermanentProgress()
    assert perm.from_dict({"upgrade_levels": levels}) is False
    for uid in IDS:
        assert perm.upgrade_levels[uid] == (0 if uid == "perm_health" else MAX_LEVELS[uid])


# --- BUG-047 boot: the real Game -----------------------------------------------------------------------

@pytest.mark.parametrize("upgrade_id", IDS)
def test_boot_level_at_max_loads_quietly(make_game, isolated_save, fixture_data, capsys, upgrade_id: str) -> None:
    """A level exactly at its max: no warning, no .bak, no notice, level kept."""
    data = copy.deepcopy(fixture_data)
    data["permanent"]["upgrade_levels"][upgrade_id] = MAX_LEVELS[upgrade_id]
    game, _raw, err = _boot(make_game, isolated_save, data, capsys)
    assert game.permanent.upgrade_levels[upgrade_id] == MAX_LEVELS[upgrade_id]
    assert err == "" and game.save_notice is None and _no_bak(isolated_save)


@pytest.mark.parametrize("upgrade_id", IDS)
@pytest.mark.parametrize("name", ["max_plus_1", "int_max", "int_max_plus_1"])
def test_boot_level_above_max_is_rejected(make_game, isolated_save, fixture_data, capsys, upgrade_id: str, name: str) -> None:
    """Above max: level 0, usual warning, .bak, partial notice; never Lv.9007199254740991/5."""
    bad = {"max_plus_1": MAX_LEVELS[upgrade_id] + 1, "int_max": INT_MAX, "int_max_plus_1": INT_MAX + 1}[name]
    data = copy.deepcopy(fixture_data)
    data["permanent"]["upgrade_levels"][upgrade_id] = bad
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    assert game.permanent.upgrade_levels[upgrade_id] == 0
    assert all(game.permanent.upgrade_levels[u] <= MAX_LEVELS[u] for u in IDS)
    assert _warned(err) and _backed_up(isolated_save, raw)
    assert game.save_notice == "partial"
    game._save_game()
    assert json.loads(isolated_save.read_text(encoding="utf-8"))["permanent"]["upgrade_levels"][upgrade_id] == 0


def test_boot_unknown_upgrade_id_is_dropped_with_warning_and_backup(make_game, isolated_save, fixture_data, capsys) -> None:
    """An unknown id warns, is backed up, is not loaded and is gone from the next save; valid entries stay."""
    data = copy.deepcopy(fixture_data)
    data["permanent"]["upgrade_levels"]["perm_damage"] = 4
    data["permanent"]["upgrade_levels"]["perm_from_the_future"] = 1
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    assert "perm_from_the_future" not in game.permanent.upgrade_levels
    assert game.permanent.upgrade_levels["perm_damage"] == 4
    assert _warned(err) and _backed_up(isolated_save, raw) and game.save_notice == "partial"
    game._save_game()
    saved = json.loads(isolated_save.read_text(encoding="utf-8"))["permanent"]["upgrade_levels"]
    assert "perm_from_the_future" not in saved and saved["perm_damage"] == 4


def test_boot_many_bad_levels_give_one_warning_one_backup_and_keep_the_good_ones(make_game, isolated_save, fixture_data, capsys) -> None:
    """Several bad entries at once: one warning, one .bak, the valid levels all survive."""
    data = copy.deepcopy(fixture_data)
    levels = {uid: MAX_LEVELS[uid] for uid in IDS}
    levels.update(perm_damage=99, perm_luck=INT_MAX, perm_ghost=2)
    data["permanent"]["upgrade_levels"] = levels
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    for uid in IDS:
        want = 0 if uid in ("perm_damage", "perm_luck") else MAX_LEVELS[uid]
        assert game.permanent.upgrade_levels[uid] == want
    assert err.count("invalid data") == 1 and _backed_up(isolated_save, raw)
    assert game.save_notice == "partial"


# --- BUG-046: non-negative bonuses ---------------------------------------------------------------------

BONUS_CASES: List[Tuple[str, Any, bool]] = [
    ("zero", 0, True),
    ("zero_float", 0.0, True),
    ("fraction", 0.15, True),
    ("tiny", 1e-9, True),
    ("big_fraction", 123456.789, True),
    ("one", 1, True),
    ("int_max", INT_MAX, True),
    ("int_max_plus_1", INT_MAX + 1, False),
    ("minus_1", -1, False),
    ("minus_tiny", -1e-9, False),
    ("minus_fraction", -0.15, False),
    ("minus_int_max", -INT_MAX, False),
    ("nan", NAN, False),
    ("inf", INF, False),
    ("minus_inf", -INF, False),
    ("huge_int", 10**400, False),
]


@pytest.mark.parametrize("name,value,kept", BONUS_CASES, ids=[c[0] for c in BONUS_CASES])
def test_number_dict_non_negative_boundaries(name: str, value: Any, kept: bool) -> None:
    """With non_negative: 0, fractions and exactly INT_MAX load; negatives, NaN, inf and INT_MAX+1 are dropped."""
    section = SaveSection({"t": {"x": value, "y": 0.5}})
    got = section.number_dict("t", {}, non_negative=True)
    assert got == ({"x": value, "y": 0.5} if kept else {"y": 0.5})
    assert section.valid is kept


def test_number_dict_still_allows_negatives_by_default() -> None:
    """The flag is opt-in: number_dict without it keeps the 022 rule (finite, within INT_MAX), negatives included."""
    section = SaveSection({"t": {"x": -2.5, "y": -INT_MAX}})
    assert section.number_dict("t", {}) == {"x": -2.5, "y": -INT_MAX} and section.valid is True


def test_negative_zero_is_not_negative() -> None:
    """-0.0 compares equal to 0 and loads quietly."""
    section = SaveSection({"t": {"x": -0.0}})
    assert section.number_dict("t", {}, non_negative=True) == {"x": -0.0} and section.valid is True


def test_bonus_int_at_int_max_loads_and_one_more_is_dropped_in_newgameplus() -> None:
    """BUG-049 (b) at the loader: 2**53-1 loads quietly, 2**53 is dropped."""
    ng = NewGamePlus()
    assert ng.from_dict({"permanent_bonuses": {"damage": 2**53 - 1}}) is True
    assert ng.permanent_bonuses["damage"] == 2**53 - 1
    ng = NewGamePlus()
    assert ng.from_dict({"permanent_bonuses": {"damage": 2**53}}) is False
    assert "damage" not in ng.permanent_bonuses


@pytest.mark.parametrize("key", BONUS_KEYS)
@pytest.mark.parametrize("name,value,kept", BONUS_CASES, ids=[c[0] for c in BONUS_CASES])
def test_boot_bonus_values(make_game, isolated_save, fixture_data, capsys, key: str, name: str, value: Any, kept: bool) -> None:
    """Real boot: kept values load quietly (no .bak, no notice); dropped ones warn, back up and give a partial notice."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["permanent_bonuses"][key] = value
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    bonuses = game.ng_plus.permanent_bonuses
    if kept:
        assert bonuses[key] == value and type(bonuses[key]) is type(value)
        assert err == "" and game.save_notice is None and _no_bak(isolated_save)
    else:
        assert key not in bonuses
        assert _warned(err) and _backed_up(isolated_save, raw) and game.save_notice == "partial"
    others = [k for k in BONUS_KEYS if k != key]
    assert all(bonuses[k] == fixture_data["ng_plus"]["permanent_bonuses"][k] for k in others)


def test_boot_bad_bonus_is_gone_from_the_next_save(make_game, isolated_save, fixture_data, capsys) -> None:
    """A dropped negative bonus is not written back as -1; the rest of the save keeps its values."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["permanent_bonuses"]["health"] = -1
    game, _raw, _err = _boot(make_game, isolated_save, data, capsys)
    game._save_game()
    saved = json.loads(isolated_save.read_text(encoding="utf-8"))["ng_plus"]["permanent_bonuses"]
    assert "health" not in saved and saved["damage"] == 0.1


def test_negative_bonus_cannot_reduce_stats(make_game, isolated_save, fixture_data, capsys) -> None:
    """The point of BUG-046: a -1 bonus no longer reaches the game's multiplier."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["permanent_bonuses"]["damage"] = -1
    game, _raw, _err = _boot(make_game, isolated_save, data, capsys)
    assert all(v >= 0 for v in game.ng_plus.permanent_bonuses.values())


# --- BUG-048: partial vs recovered ----------------------------------------------------------------------

def test_partial_notice_has_the_recovered_structure_and_narratives_exact_copy() -> None:
    """partial is in both tables with the same keys as recovered, and its copy is Narrative's, character for character."""
    from blob_evolution.ui import style

    assert set(lore.SAVE_NOTICES) == {"recovered", "partial", "saving_paused"}
    partial = lore.SAVE_NOTICES["partial"]
    assert set(partial) == set(lore.SAVE_NOTICES["recovered"]) == {"title", "body", "button"}
    assert style.NOTICE_VARIANTS["partial"].keys() == style.NOTICE_VARIANTS["recovered"].keys()
    assert partial == {
        "title": "The Lattice Half-Remembers",
        "body": "Part of your save was damaged.\nThat part began again. The rest was kept.\nYour original rests in a .bak file.",
        "button": "Carry On",
    }
    assert [len(line) for line in partial["body"].split("\n")] == [30, 41, 35]
    assert (len(partial["title"]), len(partial["button"])) == (26, 8)
    assert partial["body"].isascii() and "\r" not in partial["body"]
    source = open(lore.__file__, encoding="utf-8").read()
    assert "PLACEHOLDER" not in source and "TODO(Narrative)" not in source
    assert partial["body"] != lore.SAVE_NOTICES["recovered"]["body"]


def _set(path: Tuple[str, ...], value: Any):
    def edit(data: dict) -> dict:
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        return data
    return edit


# (id, edit to the fixture save, expected notice)
DECISIONS: List[Tuple[str, Any, str]] = [
    # a field, an entry or a whole section reset, the rest kept -> partial
    ("bad_count", _set(("permanent", "shards"), -1), "partial"),
    ("bad_count_string", _set(("ng_plus", "total_runs"), "8"), "partial"),
    ("bad_economy_field", _set(("economy", "total_earned"), 1.5), "partial"),
    ("bad_audio_flag", _set(("audio_enabled",), "false"), "partial"),
    ("level_above_max", _set(("permanent", "upgrade_levels", "perm_damage"), 6), "partial"),
    ("level_huge", _set(("permanent", "upgrade_levels", "perm_xp"), INT_MAX), "partial"),
    ("unknown_upgrade_id", _set(("permanent", "upgrade_levels", "perm_ghost"), 1), "partial"),
    ("bad_single_level", _set(("permanent", "upgrade_levels", "perm_armor"), 1.5), "partial"),
    ("negative_bonus", _set(("ng_plus", "permanent_bonuses", "damage"), -0.5), "partial"),
    ("nan_bonus", _set(("ng_plus", "permanent_bonuses", "speed"), NAN), "partial"),
    ("bad_section_ng_plus_null", _set(("ng_plus",), None), "partial"),
    ("bad_section_ng_plus_string", _set(("ng_plus",), "oops"), "partial"),
    ("bad_section_permanent_null", _set(("permanent",), None), "partial"),
    ("bad_section_permanent_list", _set(("permanent",), []), "partial"),
    ("bad_section_economy_number", _set(("economy",), 5), "partial"),
    # a whole table reset (upgrade_levels is the one named in the brief; the rest follow the same rule) -> recovered
    ("upgrade_levels_list", _set(("permanent", "upgrade_levels"), []), "recovered"),
    ("upgrade_levels_null", _set(("permanent", "upgrade_levels"), None), "recovered"),
    ("upgrade_levels_string", _set(("permanent", "upgrade_levels"), "lots"), "recovered"),
    ("upgrade_levels_number", _set(("permanent", "upgrade_levels"), 3), "recovered"),
    ("bonuses_not_a_dict", _set(("ng_plus", "permanent_bonuses"), [0.1]), "recovered"),
    ("skins_not_a_list", _set(("permanent", "unlocked_skins"), "default"), "recovered"),
    ("artifacts_not_a_list", _set(("permanent", "unlocked_artifacts"), {"a": 1}), "recovered"),
    ("wardens_not_a_list", _set(("permanent", "unlocked_wardens"), None), "recovered"),
    ("endings_not_a_list", _set(("permanent", "endings_seen"), 7), "recovered"),
]


@pytest.mark.parametrize("name,edit,expected", DECISIONS, ids=[d[0] for d in DECISIONS])
def test_boot_notice_variant_decision(make_game, isolated_save, fixture_data, capsys, name: str, edit: Any, expected: str) -> None:
    """Each damaged-but-readable save: warning, .bak and the right variant (and that variant's copy is what draws)."""
    game, raw, err = _boot(make_game, isolated_save, edit(copy.deepcopy(fixture_data)), capsys)
    assert _warned(err) and _backed_up(isolated_save, raw)
    assert game.save_notice == expected
    assert game._save_blocked is False
    assert lore.SAVE_NOTICES[game.save_notice]["title"]


UNREADABLE: List[Tuple[str, bytes]] = [
    ("garbage", b"\x00\x01 not json at all"),
    ("truncated", b'{"ng_plus": {"ng_plus_level": 2, "tot'),
    ("empty_file", b""),
    ("top_level_list", b"[1, 2, 3]"),
    ("top_level_string", b'"hello"'),
    ("top_level_number", b"42"),
    ("top_level_null", b"null"),
    ("top_level_true", b"true"),
]


@pytest.mark.parametrize("name,raw", UNREADABLE, ids=[u[0] for u in UNREADABLE])
def test_boot_unreadable_or_wrong_top_level_is_recovered(make_game, isolated_save, capsys, name: str, raw: bytes) -> None:
    """An unreadable file or a non-object top level resets everything: recovered, with the original kept in .bak."""
    game, _raw, err = _boot(make_game, isolated_save, None, capsys, raw=raw)
    assert game.save_notice == "recovered", err
    assert "[save]" in err and _backed_up(isolated_save, raw)


def test_boot_mixed_field_and_table_damage_is_recovered(make_game, isolated_save, fixture_data, capsys) -> None:
    """A bad field plus a reset table: the bigger loss wins, recovered."""
    data = copy.deepcopy(fixture_data)
    data["permanent"]["shards"] = -3
    data["permanent"]["upgrade_levels"] = "x"
    game, _raw, _err = _boot(make_game, isolated_save, data, capsys)
    assert game.save_notice == "recovered"


def test_boot_many_field_resets_in_every_section_stay_partial(make_game, isolated_save, fixture_data, capsys) -> None:
    """Partial is about the kind of damage, not the count: bad fields in all sections is still partial."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"].update(ng_plus_level=-1, total_runs=0.5)
    data["permanent"].update(shards="x", total_shards_earned=None)
    data["economy"]["total_earned"] = NAN
    data["audio_enabled"] = 0
    game, _raw, err = _boot(make_game, isolated_save, data, capsys)
    assert game.save_notice == "partial" and err.count("invalid data") == 1


def test_saving_paused_beats_partial(make_game, isolated_save, fixture_data, capsys, monkeypatch) -> None:
    """If the backup cannot be made, the paused notice still wins over partial."""
    from blob_evolution.systems import savefile

    monkeypatch.setattr(savefile, "backup_save", lambda path: False)
    data = copy.deepcopy(fixture_data)
    data["permanent"]["shards"] = -1
    game, _raw, _err = _boot(make_game, isolated_save, data, capsys)
    assert game._save_blocked is True and game.save_notice == "saving_paused"


def test_valid_save_has_no_notice_and_missing_sections_are_quiet(make_game, isolated_save, fixture_data, fixture_bytes, capsys) -> None:
    """Valid fixture, and old saves with sections or keys missing, show no notice."""
    game, _raw, err = _boot(make_game, isolated_save, None, capsys, raw=fixture_bytes)
    assert err == "" and game.save_notice is None and _no_bak(isolated_save)
    for cut in (("ng_plus",), ("permanent",), ("economy",), ("audio_enabled",), ("permanent", "upgrade_levels"),
                ("permanent", "unlocked_skins"), ("ng_plus", "permanent_bonuses")):
        data = copy.deepcopy(fixture_data)
        node = data
        for key in cut[:-1]:
            node = node[key]
        del node[cut[-1]]
        game, _raw, err = _boot(make_game, isolated_save, data, capsys)
        assert err == "" and game.save_notice is None, cut


def test_valid_save_with_levels_at_max_and_fractional_bonuses_resaves_byte_identical(make_game, isolated_save, fixture_data, capsys) -> None:
    """A valid save with every upgrade at max and fractional bonuses comes back out byte for byte."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["best_map_reached"] = 9
    data["ng_plus"]["permanent_bonuses"] = {"damage": 0.15, "health": 0.0, "speed": 0.09, "essence": 0.3}
    data["permanent"]["upgrade_levels"] = {uid: MAX_LEVELS[uid] for uid in IDS}
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    assert err == "" and game.save_notice is None
    game._save_game()
    assert isolated_save.read_bytes() == raw


def test_partial_notice_draws_over_the_main_menu_and_dismisses(make_game, isolated_save, fixture_data, capsys) -> None:
    """The partial notice shows at boot like recovered: SPACE dismisses it."""
    import pygame

    data = copy.deepcopy(fixture_data)
    data["permanent"]["shards"] = -1
    game, _raw, _err = _boot(make_game, isolated_save, data, capsys)
    assert game.save_notice == "partial"
    drawn: List[str] = []
    real = game.menu.draw_save_notice
    game.menu.draw_save_notice = lambda surf, variant, *a, **kw: (drawn.append(variant), real(surf, variant, *a, **kw))[1]
    game._draw()
    assert drawn == ["partial"]
    game._handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" "))
    assert game.save_notice is None
    game._draw()
    assert drawn == ["partial"], "gone after dismissal"
