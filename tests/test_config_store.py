import copy
import json
import os
from pathlib import Path

import pytest

from config_store import LIVE_KEYS, RANGES, ConfigChanged, known_signs, load, save, validate

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config.json"


def valid_cfg() -> dict:
    return copy.deepcopy(json.loads(REPO_CONFIG.read_text(encoding="utf-8")))


def test_save_is_atomic_and_keeps_backup(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"fps": 30}', encoding="utf-8")
    cfg, mtime = load(p)
    cfg["fps"] = 25
    save(p, cfg, mtime)
    assert json.loads(p.read_text())["fps"] == 25
    assert json.loads((tmp_path / "config.json.bak").read_text())["fps"] == 30
    assert not list(tmp_path.glob("*.tmp"))


def test_save_preserves_unknown_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"my_key": 1, "fps": 30}', encoding="utf-8")
    cfg, mtime = load(p)
    cfg["fps"] = 20
    save(p, cfg, mtime)
    assert json.loads(p.read_text()) == {"my_key": 1, "fps": 20}


def test_save_returns_new_mtime_usable_for_next_save(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"fps": 30}', encoding="utf-8")
    cfg, mtime = load(p)
    new_mtime = save(p, cfg, mtime)
    assert new_mtime == p.stat().st_mtime
    save(p, cfg, new_mtime)


def test_save_without_existing_file_makes_no_backup(tmp_path):
    p = tmp_path / "config.json"
    save(p, {"fps": 30})
    assert json.loads(p.read_text()) == {"fps": 30}
    assert not (tmp_path / "config.json.bak").exists()
    assert p.read_text().endswith("}\n")


def test_save_refuses_when_file_changed_since_load(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"fps": 30}', encoding="utf-8")
    cfg, mtime = load(p)
    p.write_text('{"fps": 99}', encoding="utf-8")
    os.utime(p, (mtime + 10, mtime + 10))
    with pytest.raises(ConfigChanged):
        save(p, cfg, mtime)
    assert json.loads(p.read_text())["fps"] == 99


def test_validate_reports_each_bad_field():
    cfg = valid_cfg()
    cfg["hold_frames"] = 0
    cfg["quality"] = "ultra"
    cfg["domains"]["idle_death_gamble"]["hotkey"] = "<ctrl>+<nope>"
    cfg["actions"] = {"mute": {}, "unlimited_void": {"keys": "a"}, "bad name!": {"keys": "a"}}
    errors = validate(cfg)
    assert set(errors) >= {"hold_frames", "quality", "domains.idle_death_gamble.hotkey",
                           "actions.mute", "actions.unlimited_void", "actions.bad name!"}


def test_validate_rejects_non_integer_and_out_of_range_numbers():
    cfg = valid_cfg()
    cfg["hold_frames"] = 2.5
    cfg["fps"] = 61
    cfg["cooldown_sec"] = -1
    cfg["width"] = True
    errors = validate(cfg)
    assert {"hold_frames", "fps", "cooldown_sec", "width"} <= set(errors)
    assert "miss_tolerance" not in errors


def test_validate_requires_booleans_for_preview_flags():
    cfg = valid_cfg()
    cfg["show_preview"] = "yes"
    cfg["mirror_preview"] = 1
    assert {"show_preview", "mirror_preview"} <= set(validate(cfg))


def test_validate_rejects_duplicate_hotkeys():
    cfg = valid_cfg()
    cfg["domains"]["unlimited_void"]["hotkey"] = "<ctrl>+<alt>+d"
    cfg["domains"]["malevolent_shrine"]["hotkey"] = "<ctrl>+<alt>+d"
    errors = validate(cfg)
    assert "domains.unlimited_void.hotkey" in errors
    assert "domains.malevolent_shrine.hotkey" in errors
    assert "domains.idle_death_gamble.hotkey" not in errors


def test_validate_rejects_loop_end_before_start():
    cfg = valid_cfg()
    cfg["domains"]["unlimited_void"]["loop_start_sec"] = 3.0
    cfg["domains"]["unlimited_void"]["loop_end_sec"] = 2.0
    errors = validate(cfg)
    assert "domains.unlimited_void.loop_end_sec" in errors


def test_validate_rejects_negative_loop_start_and_bad_keywords():
    cfg = valid_cfg()
    cfg["domains"]["unlimited_void"]["loop_start_sec"] = -1
    cfg["domains"]["malevolent_shrine"]["keywords"] = ["ok", 3]
    errors = validate(cfg)
    assert "domains.unlimited_void.loop_start_sec" in errors
    assert "domains.malevolent_shrine.keywords" in errors


def test_validate_rejects_bad_domain_name():
    cfg = valid_cfg()
    cfg["domains"]["bad name!"] = {"video": "", "keywords": [], "loop_start_sec": 0,
                                   "loop_end_sec": None, "hotkey": "<ctrl>+<alt>+x"}
    assert "domains.bad name!" in validate(cfg)


def test_validate_rejects_action_with_two_types_or_blank_value():
    cfg = valid_cfg()
    cfg["actions"] = {"both": {"keys": "a", "type": "b"}, "blank": {"type": "  "}}
    errors = validate(cfg)
    assert {"actions.both", "actions.blank"} <= set(errors)


def test_validate_accepts_config_without_optional_sections():
    cfg = valid_cfg()
    cfg.pop("actions")
    cfg["domains"]["unlimited_void"].pop("title", None)
    assert validate(cfg) == {}


def test_validate_accepts_repo_config():
    assert validate(valid_cfg()) == {}


def test_live_keys_and_ranges_are_declared():
    assert set(LIVE_KEYS) == {"hold_frames", "miss_tolerance", "cooldown_sec", "quality",
                              "show_preview", "preview_width", "mirror_preview", "actions"}
    assert RANGES["hold_frames"] == (1, 120)
    assert RANGES["preview_width"] == (160, 1920)


def test_known_signs_includes_taught_folders(tmp_path):
    for label in ("mute", "none"):
        (tmp_path / label).mkdir()
        (tmp_path / label / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "README.txt").write_text("x", encoding="utf-8")
    signs = known_signs(valid_cfg(), tmp_path)
    assert signs == sorted(signs)
    assert "mute" in signs
    assert "none" not in signs
    assert {"unlimited_void", "malevolent_shrine", "idle_death_gamble"} <= set(signs)


def test_known_signs_without_samples_dir(tmp_path):
    assert "unlimited_void" in known_signs({}, tmp_path / "missing")
