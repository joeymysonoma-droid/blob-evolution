"""TASK-007 save-hardening regressions (QA verification items 2-8).

All run in tmp_path via the autouse ``isolated_save`` fixture in conftest.py.
Game._save_game() is called directly; it is the same method the game calls on
exit (after QUIT / SIGTERM), on purchases and at run end.
"""

from __future__ import annotations

import copy
import json
import os
import stat

import pytest

from blob_evolution import config

UNREADABLE = {
    "05_zero_byte_file": b"",
    "07_non_json_text": b"this is not json\n",
    "08_non_utf8_bytes": b"\xff\xfe\x00\x81garbage\x9c",
    "09_top_level_list": b"[]",
}


def _bak(save, n=0):
    """Path of backup slot n (0 -> .bak, 1 -> .bak.1, ...)."""
    base = str(save) + config.SAVE_BACKUP_SUFFIX
    return type(save)(base if n == 0 else f"{base}.{n}")


def _save_files(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("blob_evolution_save"))


@pytest.fixture
def default_save_bytes(make_game, isolated_save):
    """Bytes the game writes when there is no save at all (then removed again)."""
    assert not isolated_save.exists()
    make_game()._save_game()
    data = isolated_save.read_bytes()
    isolated_save.unlink()
    return data


def _boot_and_save(make_game):
    game = make_game()
    game._save_game()
    return game


# --- item 2: unreadable / invalid saves -> exact backup + valid new save ----------------------

@pytest.mark.parametrize("raw", list(UNREADABLE.values()), ids=list(UNREADABLE))
def test_unreadable_save_backed_up_then_defaults(make_game, isolated_save, default_save_bytes, raw):
    isolated_save.write_bytes(raw)
    _boot_and_save(make_game)
    assert _bak(isolated_save).read_bytes() == raw
    assert isolated_save.read_bytes() == default_save_bytes


def test_truncated_save_backed_up_then_defaults(make_game, isolated_save, default_save_bytes, fixture_bytes):
    raw = fixture_bytes[: len(fixture_bytes) // 2]  # edge case 06
    isolated_save.write_bytes(raw)
    _boot_and_save(make_game)
    assert _bak(isolated_save).read_bytes() == raw
    assert isolated_save.read_bytes() == default_save_bytes


def test_null_section_backed_up_and_only_that_section_defaulted(
    make_game, isolated_save, default_save_bytes, fixture_data
):
    data = copy.deepcopy(fixture_data)  # edge case 10
    data["ng_plus"] = None
    raw = json.dumps(data, indent=2).encode()
    isolated_save.write_bytes(raw)
    _boot_and_save(make_game)
    assert _bak(isolated_save).read_bytes() == raw
    written = json.loads(isolated_save.read_bytes())
    assert written["ng_plus"] == json.loads(default_save_bytes)["ng_plus"]
    assert written["permanent"] == fixture_data["permanent"]
    assert written["economy"]["total_earned"] == fixture_data["economy"]["total_earned"]


# --- item 3: valid / old saves -> no backup, values preserved, atomic write leaves no temp ----

def test_valid_fixture_no_backup_and_byte_identical(make_game, isolated_save, fixture_bytes, tmp_path):
    isolated_save.write_bytes(fixture_bytes)
    _boot_and_save(make_game)
    assert _save_files(tmp_path) == [isolated_save.name]  # no .bak, no leftover .tmp
    assert isolated_save.read_bytes() == fixture_bytes


def test_empty_object_save_no_backup(make_game, isolated_save, default_save_bytes, tmp_path):
    isolated_save.write_text("{}")
    _boot_and_save(make_game)
    assert _save_files(tmp_path) == [isolated_save.name]
    assert isolated_save.read_bytes() == default_save_bytes


def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[prefix + k] = v
    return out


def _drop_top(d):
    for k in ("economy", "audio_enabled", "ng_plus"):
        del d[k]


def _drop_nested(d):
    for k in ("unlocked_wardens", "unlocked_artifacts", "endings_seen", "equipped_skin", "unlocked_skins"):
        del d["permanent"][k]
    for k in ("perm_crit", "perm_luck", "perm_essence", "perm_shards", "perm_start_sp", "perm_start_essence"):
        del d["permanent"]["upgrade_levels"][k]
    del d["ng_plus"]["permanent_bonuses"]
    del d["ng_plus"]["best_map_reached"]
    del d["economy"]["total_earned"]


@pytest.mark.parametrize("mutate", [_drop_top, _drop_nested], ids=["missing_top_keys", "missing_nested_keys"])
def test_old_save_missing_keys_no_backup_values_preserved(make_game, isolated_save, fixture_data, tmp_path, mutate):
    data = copy.deepcopy(fixture_data)
    mutate(data)
    isolated_save.write_text(json.dumps(data, indent=2))
    _boot_and_save(make_game)
    assert _save_files(tmp_path) == [isolated_save.name]
    written = _flatten(json.loads(isolated_save.read_bytes()))
    for key, value in _flatten(data).items():
        assert written[key] == value, key


# --- item 4: no save at all -> no backup, silent -------------------------------------------

def test_no_save_file_no_backup_no_warning(make_game, isolated_save, tmp_path, capsys):
    capsys.readouterr()
    _boot_and_save(make_game)
    out, err = capsys.readouterr()
    assert "[save]" not in out
    assert err == ""
    assert _save_files(tmp_path) == [isolated_save.name]


# --- item 5: backup dedupe / rotation ------------------------------------------------------

def test_same_bad_file_twice_gives_one_backup(make_game, isolated_save, tmp_path):
    raw = b"this is not json\n"
    for _ in range(2):
        isolated_save.write_bytes(raw)
        _boot_and_save(make_game)
    assert _save_files(tmp_path) == [isolated_save.name, _bak(isolated_save).name]
    assert _bak(isolated_save).read_bytes() == raw


def test_different_bad_files_use_next_slot(make_game, isolated_save, fixture_bytes):
    first, second = b"this is not json\n", fixture_bytes[: len(fixture_bytes) // 2]
    isolated_save.write_bytes(first)
    _boot_and_save(make_game)
    isolated_save.write_bytes(second)
    _boot_and_save(make_game)
    assert _bak(isolated_save, 0).read_bytes() == first
    assert _bak(isolated_save, 1).read_bytes() == second


# --- item 6: backup impossible -> save blocked, original untouched --------------------------

def test_all_backup_slots_full_blocks_save(make_game, isolated_save, fixture_bytes, tmp_path):
    raw = fixture_bytes[: len(fixture_bytes) // 2]
    isolated_save.write_bytes(raw)
    slots = {}
    for n in range(config.SAVE_BACKUP_LIMIT):
        slots[n] = f"prefilled slot {n}\n".encode()
        _bak(isolated_save, n).write_bytes(slots[n])
    game = _boot_and_save(make_game)
    assert game._save_blocked is True
    assert isolated_save.read_bytes() == raw
    for n, content in slots.items():
        assert _bak(isolated_save, n).read_bytes() == content
    assert len(_save_files(tmp_path)) == 1 + config.SAVE_BACKUP_LIMIT


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions")
def test_read_only_dir_bad_save_untouched(make_game, isolated_save, fixture_bytes, tmp_path):
    raw = fixture_bytes[: len(fixture_bytes) // 2]
    isolated_save.write_bytes(raw)
    mode = tmp_path.stat().st_mode
    tmp_path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        game = _boot_and_save(make_game)
    finally:
        tmp_path.chmod(mode)
    assert game._save_blocked is True
    assert isolated_save.read_bytes() == raw
    assert _save_files(tmp_path) == [isolated_save.name]


# --- item 7: wrong-typed fields -> backup + field falls back to its default ------------------

def _set_upgrade_levels_null(d):
    d["permanent"]["upgrade_levels"] = None
    return "upgrade_levels"


def _set_shards_string(d):
    d["permanent"]["shards"] = "72"
    return "shards"


def _set_total_earned_nan(d):
    d["economy"]["total_earned"] = float("nan")
    return "total_earned"


@pytest.mark.parametrize(
    "mutate", [_set_upgrade_levels_null, _set_shards_string, _set_total_earned_nan],
    ids=["upgrade_levels_null", "shards_string", "total_earned_nan"],
)
def test_wrong_typed_field_backed_up_and_defaulted(
    make_game, isolated_save, fixture_data, default_save_bytes, mutate
):
    data = copy.deepcopy(fixture_data)
    field = mutate(data)
    raw = json.dumps(data, indent=2).encode()  # NaN serialises as the bare token NaN
    isolated_save.write_bytes(raw)
    _boot_and_save(make_game)
    assert _bak(isolated_save).read_bytes() == raw
    text = isolated_save.read_text()
    assert "NaN" not in text
    written, defaults = json.loads(text), json.loads(default_save_bytes)
    section = "economy" if field == "total_earned" else "permanent"
    assert written[section][field] == defaults[section][field]


# --- item 8: failed atomic write leaves the old save intact ---------------------------------

def test_failed_write_keeps_previous_save(make_game, isolated_save, fixture_bytes):
    isolated_save.write_bytes(fixture_bytes)
    (isolated_save.parent / (isolated_save.name + config.SAVE_TEMP_SUFFIX)).mkdir()
    _boot_and_save(make_game)
    assert isolated_save.read_bytes() == fixture_bytes
