"""TASK-022 (BUG-006, BUG-026, BUG-027): save fields are read with strict types.

Counts and levels must be whole numbers 0..INT_MAX (so 9.5, -1, 3.0, True, "5", null, NaN, inf and huge ints
fall back to their default); audio_enabled must be a real JSON true/false. A rejected field takes 007's
safe-default path: the field loads as its default, a [save] warning is printed and the file is backed up.

Everything goes through the real loaders: SaveSection, the from_dict methods and a real Game boot.
"""

from __future__ import annotations

import copy
import inspect
import json
from typing import Any, Callable, Dict, List, Tuple

import pytest

from blob_evolution import config
from blob_evolution.systems import newgameplus
from blob_evolution.systems.newgameplus import NewGamePlus
from blob_evolution.systems.permanent import PERMANENT_UPGRADES, PermanentProgress
from blob_evolution.systems.savefile import INT_MAX, SaveSection

NAN, INF = float("nan"), float("inf")
# (id, value): every one is rejected for a count / level field
BAD_COUNTS: List[Tuple[str, Any]] = [
    ("negative", -1),
    ("negative_five", -5),
    ("fraction", 9.5),
    ("whole_float", 3.0),
    ("zero_float", 0.0),
    ("negative_float", -2.0),
    ("string", "5"),
    ("true", True),
    ("false", False),
    ("null", None),
    ("list", [1]),
    ("nan", NAN),
    ("inf", INF),
    ("minus_inf", -INF),
    ("just_over_max", INT_MAX + 1),
    ("huge_int", 10**400),
]
GOOD_COUNTS: List[Tuple[str, int]] = [("zero", 0), ("small", 7), ("max", INT_MAX)]
# every one is rejected for a bool field (audio_enabled)
BAD_BOOLS: List[Tuple[str, Any]] = [
    ("string_false", "false"),
    ("string_true", "true"),
    ("empty_string", ""),
    ("string_0", "0"),
    ("int_0", 0),
    ("int_1", 1),
    ("float_0", 0.0),
    ("float_1", 1.0),
    ("null", None),
    ("list", []),
    ("dict", {}),
]

# field id -> (path into the save, reader of the loaded value from a Game, value the game uses by default)
COUNT_FIELDS: Dict[str, Tuple[Tuple[str, ...], Callable[[Any], Any], int]] = {
    "ng_plus_level": (("ng_plus", "ng_plus_level"), lambda g: g.ng_plus.ng_plus_level, 0),
    "total_runs": (("ng_plus", "total_runs"), lambda g: g.ng_plus.total_runs, 0),
    "best_map_reached": (("ng_plus", "best_map_reached"), lambda g: g.ng_plus.best_map_reached, 0),
    "shards": (("permanent", "shards"), lambda g: g.permanent.shards, 0),
    "total_shards_earned": (("permanent", "total_shards_earned"), lambda g: g.permanent.total_shards_earned, 0),
    "upgrade_level": (("permanent", "upgrade_levels", "perm_damage"), lambda g: g.permanent.upgrade_levels["perm_damage"], 0),
    "total_earned": (("economy", "total_earned"), lambda g: g.economy.total_earned, 0),
}
BAK = config.SAVE_BACKUP_SUFFIX
UPGRADE_MAX = {u["id"]: u["max_level"] for u in PERMANENT_UPGRADES}


def _with(data: dict, path: Tuple[str, ...], value: Any, base_ng_level: int = 2) -> dict:
    """Copy of the save with one field set (NG+ level pinned so best_map_reached's clamp is predictable)."""
    out = copy.deepcopy(data)
    out["ng_plus"]["ng_plus_level"] = base_ng_level
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def _boot(make_game, isolated_save, data: dict, capsys):
    """Write data (NaN/Infinity tokens allowed, as json.dumps writes them), boot a real Game, return (game, raw, stderr)."""
    raw = json.dumps(data, indent=2).encode()
    isolated_save.write_bytes(raw)
    capsys.readouterr()
    game = make_game()
    return game, raw, capsys.readouterr().err


def _backed_up(isolated_save, raw: bytes) -> bool:
    """True if the .bak slot holds exactly the original bytes."""
    bak = isolated_save.parent / (isolated_save.name + BAK)
    return bak.exists() and bak.read_bytes() == raw


# --- SaveSection, directly ----------------------------------------------------------------------

@pytest.mark.parametrize("name,value", BAD_COUNTS, ids=[n for n, _ in BAD_COUNTS])
def test_integer_rejects_non_counts(name: str, value: Any) -> None:
    """SaveSection.integer returns the default and marks the section invalid."""
    section = SaveSection({"n": value})
    assert section.integer("n", 4) == 4
    assert section.valid is False


@pytest.mark.parametrize("name,value", GOOD_COUNTS, ids=[n for n, _ in GOOD_COUNTS])
def test_integer_accepts_whole_numbers_up_to_int_max(name: str, value: int) -> None:
    """0, small values and exactly INT_MAX load unchanged and stay ints."""
    section = SaveSection({"n": value})
    got = section.integer("n", 4)
    assert got == value and type(got) is int
    assert section.valid is True


def test_integer_missing_key_is_the_default_and_valid() -> None:
    """A missing key is an old save, not a bad one."""
    section = SaveSection({})
    assert section.integer("n", 4) == 4 and section.valid is True


def test_int_max_is_the_exact_float_limit() -> None:
    """INT_MAX is 2**53 - 1: the biggest int a float holds exactly; the next one is not accepted."""
    assert INT_MAX == 2**53 - 1
    assert float(INT_MAX) == INT_MAX and float(INT_MAX + 2) != INT_MAX + 2
    assert SaveSection({"n": INT_MAX + 1}).integer("n", 0) == 0


@pytest.mark.parametrize("name,value", BAD_BOOLS, ids=[n for n, _ in BAD_BOOLS])
def test_boolean_rejects_non_bools(name: str, value: Any) -> None:
    """SaveSection.boolean returns the default for strings, ints, floats, null and containers."""
    for default in (True, False):
        section = SaveSection({"b": value})
        assert section.boolean("b", default) is default
        assert section.valid is False


@pytest.mark.parametrize("value", [True, False])
def test_boolean_accepts_real_bools(value: bool) -> None:
    """JSON true / false load as given."""
    section = SaveSection({"b": value})
    assert section.boolean("b", not value) is value and section.valid is True


def test_integer_dict_keeps_good_entries_and_flags_the_rest() -> None:
    """Bad upgrade levels are dropped one by one; the section turns invalid."""
    levels = {"a": 1, "b": 2.5, "c": True, "d": -1, "e": "3", "f": 0, "g": 3.0, "h": INT_MAX + 1}
    section = SaveSection({"levels": levels})
    assert section.integer_dict("levels", {}) == {"a": 1, "f": 0}
    assert section.valid is False


def test_number_still_takes_fractions_but_not_nan_inf_or_huge_ints() -> None:
    """number / number_dict (NG+ bonuses are genuine fractions) keep fractions, and reject NaN, inf and huge ints."""
    assert SaveSection({"x": 0.05}).number("x", 0.0) == 0.05
    for bad in (NAN, INF, -INF, 10**400, INT_MAX + 1, True, "0.1", None):
        section = SaveSection({"x": bad})
        assert section.number("x", 0.0) == 0.0 and section.valid is False
    section = SaveSection({"b": {"damage": 0.1, "health": NAN, "speed": 10**400, "essence": True}})
    assert section.number_dict("b", {}) == {"damage": 0.1} and section.valid is False


# --- the from_dict loaders ----------------------------------------------------------------------

def test_ng_plus_from_dict_uses_defaults_and_reports_bad_fields() -> None:
    """Bad NG+ counts load as 0 and from_dict returns False."""
    ng = NewGamePlus()
    ok = ng.from_dict({"ng_plus_level": 9.5, "total_runs": -1, "best_map_reached": True, "permanent_bonuses": {}})
    assert ok is False
    assert (ng.ng_plus_level, ng.total_runs, ng.best_map_reached) == (0, 0, 0)


@pytest.mark.parametrize("name,value", [c for c in BAD_COUNTS if c[0] in ("fraction", "negative", "nan", "whole_float")])
def test_ng_plus_bad_level_never_unlocks_the_best_clamp(name: str, value: Any) -> None:
    """A rejected level is NG+ 0, so best_map_reached keeps its stored value (no clamp to 9)."""
    ng = NewGamePlus()
    ng.from_dict({"ng_plus_level": value, "total_runs": 1, "best_map_reached": 3})
    assert ng.ng_plus_level == 0 and ng.best_map_reached == 3


def test_ng_plus_clamp_still_raises_a_low_best_at_level_1() -> None:
    """The 013c rule is unchanged: NG+ 1+ with a low best loads best 9; a higher best is kept."""
    for stored, expected in ((1, 9), (9, 9), (12, 12)):
        ng = NewGamePlus()
        assert ng.from_dict({"ng_plus_level": 1, "total_runs": 1, "best_map_reached": stored}) is True
        assert ng.best_map_reached == expected


def test_bad_best_at_ng_plus_2_falls_back_then_clamps() -> None:
    """A rejected best (9.5) is 0, then the NG+ 2 clamp lifts it to 9."""
    ng = NewGamePlus()
    assert ng.from_dict({"ng_plus_level": 2, "total_runs": 1, "best_map_reached": 9.5}) is False
    assert ng.best_map_reached == 9


def test_newgameplus_has_no_private_is_number_or_stale_comment() -> None:
    """BUG-026: the duplicate _is_number (which let inf / NaN through) and its 'load as they always did' comment are gone."""
    assert not hasattr(newgameplus, "_is_number")
    source = inspect.getsource(newgameplus)
    assert "_is_number" not in source
    assert "Malformed values skip the clamp" not in source


def test_permanent_from_dict_rejects_bad_counts() -> None:
    """Shards and upgrade levels use the same whole-number rule."""
    perm = PermanentProgress()
    ok = perm.from_dict({
        "shards": 12.5, "total_shards_earned": -3,
        "upgrade_levels": {"perm_damage": 2, "perm_health": 1.5, "perm_speed": True},
    })
    assert ok is False
    assert perm.shards == 0 and perm.total_shards_earned == 0
    assert perm.upgrade_levels["perm_damage"] == 2
    assert perm.upgrade_levels["perm_health"] == 0 and perm.upgrade_levels["perm_speed"] == 0


# --- real Game boot: every odd value, warning and .bak ------------------------------------------

@pytest.mark.parametrize("field", list(COUNT_FIELDS))
@pytest.mark.parametrize("name,value", BAD_COUNTS, ids=[n for n, _ in BAD_COUNTS])
def test_boot_bad_count_falls_back_with_warning_and_backup(
    make_game, isolated_save, fixture_data, capsys, field: str, name: str, value: Any
) -> None:
    """A wrong-typed count loads as its default, warns on stderr and is backed up byte for byte."""
    path, read, default = COUNT_FIELDS[field]
    # best_map_reached: at NG+ 0 the clamp is off, so the default 0 is visible
    base_level = 0 if field == "best_map_reached" else 2
    game, raw, err = _boot(make_game, isolated_save, _with(fixture_data, path, value, base_level), capsys)
    assert read(game) == default, (field, name)
    assert "[save]" in err and "invalid data" in err, err
    assert _backed_up(isolated_save, raw)
    assert game.save_notice == "partial"
    game._save_game()
    text = isolated_save.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text


@pytest.mark.parametrize("field", list(COUNT_FIELDS))
@pytest.mark.parametrize("name,value", GOOD_COUNTS, ids=[n for n, _ in GOOD_COUNTS])
def test_boot_good_count_loads_unchanged_without_warning(
    make_game, isolated_save, fixture_data, capsys, field: str, name: str, value: int
) -> None:
    """0, small and INT_MAX values load as given, with no warning, no .bak and no notice."""
    path, read, _default = COUNT_FIELDS[field]
    base_level = 0 if field == "best_map_reached" else 2
    if field == "upgrade_level":
        value = min(value, UPGRADE_MAX["perm_damage"])  # TASK-023: a level above its max is rejected now
    game, _raw, err = _boot(make_game, isolated_save, _with(fixture_data, path, value, base_level), capsys)
    assert read(game) == value
    assert err == ""
    assert not (isolated_save.parent / (isolated_save.name + BAK)).exists()
    assert game.save_notice is None


def test_boot_best_minus_5_at_ng_plus_0_is_default() -> None:
    """BUG-027's own example: best -5 at NG+ 0 loads as 0 (the loader, no clamp involved)."""
    ng = NewGamePlus()
    assert ng.from_dict({"ng_plus_level": 0, "total_runs": 0, "best_map_reached": -5}) is False
    assert ng.best_map_reached == 0


@pytest.mark.parametrize("name,value", BAD_BOOLS, ids=[n for n, _ in BAD_BOOLS])
def test_boot_bad_audio_enabled_uses_default_with_warning_and_backup(
    make_game, isolated_save, fixture_data, capsys, name: str, value: Any
) -> None:
    """BUG-006: a wrong-typed audio_enabled is the default (on), not bool(value); it warns and is backed up."""
    data = copy.deepcopy(fixture_data)
    data["audio_enabled"] = value
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    assert game.audio.enabled is True, "falls back to the default, never to bool(value)"
    assert "[save]" in err and "invalid data" in err, err
    assert _backed_up(isolated_save, raw)
    assert game.save_notice == "partial"


def test_boot_audio_off_is_remembered_and_true_loads_quietly(make_game, isolated_save, fixture_data, capsys) -> None:
    """Real JSON false turns audio off; real true keeps it on; neither warns or backs up."""
    for value in (False, True):
        data = copy.deepcopy(fixture_data)
        data["audio_enabled"] = value
        game, _raw, err = _boot(make_game, isolated_save, data, capsys)
        assert game.audio.enabled is value
        assert err == "" and game.save_notice is None
    assert not (isolated_save.parent / (isolated_save.name + BAK)).exists()


def test_boot_bad_audio_enabled_is_rewritten_as_a_real_bool(make_game, isolated_save, fixture_data, capsys) -> None:
    """After a recovered boot the next save holds a real JSON boolean."""
    data = copy.deepcopy(fixture_data)
    data["audio_enabled"] = "false"
    game, _raw, _err = _boot(make_game, isolated_save, data, capsys)
    game._save_game()
    assert json.loads(isolated_save.read_text(encoding="utf-8"))["audio_enabled"] is True


def test_audio_enabled_is_the_only_bool_in_the_save(make_game, isolated_save, fixture_data, capsys) -> None:
    """Guard for BUG-006's 'every bool field': the game's own save has exactly one bool value, audio_enabled."""
    game, _raw, _err = _boot(make_game, isolated_save, fixture_data, capsys)
    game._save_game()
    saved = json.loads(isolated_save.read_text(encoding="utf-8"))

    def bools(node: Any, path: str = "") -> List[str]:
        if isinstance(node, bool):
            return [path]
        if isinstance(node, dict):
            return [p for k, v in node.items() for p in bools(v, f"{path}.{k}" if path else k)]
        if isinstance(node, list):
            return [p for i, v in enumerate(node) for p in bools(v, f"{path}[{i}]")]
        return []

    assert bools(saved) == ["audio_enabled"]


def test_several_bad_fields_give_one_backup_and_one_warning(make_game, isolated_save, fixture_data, capsys) -> None:
    """Many odd fields at once: each falls back, the file is backed up once, one 'invalid data' line."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["ng_plus_level"] = 9.5
    data["permanent"]["shards"] = -4
    data["permanent"]["upgrade_levels"]["perm_xp"] = 3.0
    data["economy"]["total_earned"] = True
    data["audio_enabled"] = 1
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    assert game.ng_plus.ng_plus_level == 0 and game.permanent.shards == 0
    assert game.permanent.upgrade_levels["perm_xp"] == 0 and game.economy.total_earned == 0
    assert game.audio.enabled is True
    assert err.count("invalid data") == 1 and "backed up" in err
    assert _backed_up(isolated_save, raw)
    assert not (isolated_save.parent / (isolated_save.name + BAK + ".1")).exists()


# --- valid saves are unchanged ------------------------------------------------------------------

def test_fixture_loads_quietly_and_resaves_as_before(make_game, isolated_save, fixture_bytes, capsys) -> None:
    """The repo fixture: no warning, no .bak, and a re-save differs only by the 013c best 1 -> 9 change."""
    isolated_save.write_bytes(fixture_bytes)
    capsys.readouterr()
    game = make_game()
    assert capsys.readouterr().err == ""
    assert game.save_notice is None and not _backed_up(isolated_save, fixture_bytes)
    game._save_game()
    expected = fixture_bytes.replace(b'"best_map_reached": 1', b'"best_map_reached": 9')
    assert expected != fixture_bytes and isolated_save.read_bytes() == expected


def test_valid_save_without_the_013c_change_resaves_byte_identical(make_game, isolated_save, fixture_data, capsys) -> None:
    """A valid save whose best is already Layer 10 re-saves byte for byte, ints staying ints."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["best_map_reached"] = 9
    raw = json.dumps(data, indent=2).encode()
    isolated_save.write_bytes(raw)
    capsys.readouterr()
    game = make_game()
    assert capsys.readouterr().err == ""
    game._save_game()
    assert isolated_save.read_bytes() == raw


def test_valid_ng_plus_zero_save_resaves_byte_identical(make_game, isolated_save, fixture_data, capsys) -> None:
    """NG+ 0 saves have no clamp, so even the fixture's low best round-trips untouched."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"].update(ng_plus_level=0, best_map_reached=3)
    raw = json.dumps(data, indent=2).encode()
    isolated_save.write_bytes(raw)
    capsys.readouterr()
    game = make_game()
    assert capsys.readouterr().err == ""
    game._save_game()
    assert isolated_save.read_bytes() == raw


def test_audio_off_valid_save_resaves_byte_identical(make_game, isolated_save, fixture_data, capsys) -> None:
    """A valid save with audio off round-trips untouched."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["best_map_reached"] = 9
    data["audio_enabled"] = False
    raw = json.dumps(data, indent=2).encode()
    isolated_save.write_bytes(raw)
    game = make_game()
    game._save_game()
    assert isolated_save.read_bytes() == raw and game.audio.enabled is False


def test_float_bonuses_and_economy_fields_not_loaded_stay_valid(make_game, isolated_save, fixture_data, capsys) -> None:
    """permanent_bonuses are real fractions and economy.essence / run_damage_boost are never read: both stay quiet."""
    data = copy.deepcopy(fixture_data)
    data["economy"].update(essence=123.5, run_damage_boost=0.25)
    data["ng_plus"]["permanent_bonuses"] = {"damage": 0.15, "health": 0.15, "speed": 0.09, "essence": 0.3}
    game, _raw, err = _boot(make_game, isolated_save, data, capsys)
    assert err == "" and game.save_notice is None
    assert game.ng_plus.permanent_bonuses == data["ng_plus"]["permanent_bonuses"]


@pytest.mark.parametrize("bad", [NAN, INF, 10**400, "0.1", True])
def test_bad_ng_plus_bonus_value_is_dropped_with_backup(make_game, isolated_save, fixture_data, capsys, bad: Any) -> None:
    """A NaN / inf / huge / non-number bonus is dropped (the key is gone), with warning and .bak."""
    data = copy.deepcopy(fixture_data)
    data["ng_plus"]["permanent_bonuses"]["damage"] = bad
    game, raw, err = _boot(make_game, isolated_save, data, capsys)
    assert "damage" not in game.ng_plus.permanent_bonuses
    assert "invalid data" in err and _backed_up(isolated_save, raw)
