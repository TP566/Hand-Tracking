import copy
import json
import os
from pathlib import Path

import pytest

import config_store
from actions import Actions
from gesture_trigger import HoldTrigger
from live_config import ConfigWatcher, LiveResult, apply_live
from pipeline import QUALITY_LEVELS, QualityGovernor

# A frozen copy: the real config.json is the user's, and changes as they use the settings window.
FIXTURE_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config.json"


def base_cfg() -> dict:
    return copy.deepcopy(json.loads(FIXTURE_CONFIG.read_text(encoding="utf-8")))


@pytest.fixture
def old():
    return base_cfg()


@pytest.fixture
def triggers(old):
    return {name: HoldTrigger(old["hold_frames"], old["cooldown_sec"], old["miss_tolerance"])
            for name in ("a", "b", "c")}


@pytest.fixture
def gov():
    return QualityGovernor("auto")


@pytest.fixture
def acts(old):
    return Actions(copy.deepcopy(old["actions"]), runner=lambda action: None)


def test_sensitivity_applied_to_all_triggers(old, triggers, gov, acts):
    new = {**old, "hold_frames": 20, "miss_tolerance": 5, "cooldown_sec": 3.0}
    r = apply_live(old, new, triggers, gov, acts)
    assert all((t.hold_frames, t.miss_tolerance, t.cooldown_sec) == (20, 5, 3.0)
               for t in triggers.values())
    assert r.applied == ["hold_frames", "miss_tolerance", "cooldown_sec"]
    assert r.restart == [] and r.warnings == []


def test_unchanged_config_applies_nothing(old, triggers, gov, acts):
    triggers["a"].hold_frames = 99      # would be overwritten if unchanged keys were applied
    r = apply_live(old, copy.deepcopy(old), triggers, gov, acts)
    assert r.applied == [] and r.restart == [] and r.warnings == [] and not r.quality_changed
    assert triggers["a"].hold_frames == 99


def test_quality_and_preview_applied(old, triggers, acts):
    gov = QualityGovernor("low")
    old["quality"] = "low"
    new = {**old, "quality": "high", "show_preview": False, "preview_width": 320,
           "mirror_preview": False}
    r = apply_live(old, new, triggers, gov, acts)
    assert gov.mode == "high" and gov.level == 0
    assert r.quality_changed
    assert r.preview == {"show_preview": False, "preview_width": 320, "mirror_preview": False}
    assert set(r.applied) == {"quality", "show_preview", "preview_width", "mirror_preview"}


def test_quality_to_auto_keeps_level_and_reports_no_level_change(old, triggers, acts):
    gov = QualityGovernor("low")
    old["quality"] = "low"
    r = apply_live(old, {**old, "quality": "auto"}, triggers, gov, acts)
    assert gov.mode == "auto" and gov.level == len(QUALITY_LEVELS) - 1
    assert "quality" in r.applied and not r.quality_changed


def test_preview_reports_current_values_even_when_unchanged(old, triggers, gov, acts):
    r = apply_live(old, {**old, "hold_frames": 7}, triggers, gov, acts)
    assert r.preview == {"show_preview": True, "preview_width": 640, "mirror_preview": True}


def test_removed_optional_keys_fall_back_to_defaults(old, triggers, gov, acts):
    new = {k: v for k, v in old.items() if k not in ("miss_tolerance", "show_preview")}
    old["miss_tolerance"] = 8
    r = apply_live(old, new, triggers, gov, acts)
    assert all(t.miss_tolerance == 3 for t in triggers.values())
    assert r.preview["show_preview"] is True
    assert r.applied == ["miss_tolerance"]


def test_actions_swapped(old, triggers, gov, acts):
    new = {**old, "actions": {"deafen": {"keys": "ctrl+shift+f10"}, "wave": {"type": "hi"}}}
    r = apply_live(old, new, triggers, gov, acts)
    assert acts.actions == new["actions"] and "mute" not in acts
    assert r.applied == ["actions"] and r.warnings == []


def test_bad_action_entry_dropped_and_rest_applied(old, triggers, gov, acts, capsys):
    new = {**old, "actions": {"good": {"keys": "a"}, "bad": {"keys": "a", "type": "b"}}}
    r = apply_live(old, new, triggers, gov, acts)
    assert acts.actions == {"good": {"keys": "a"}}
    assert "actions" in r.applied
    assert "[bad] Ignoring action" in capsys.readouterr().out


def test_action_clash_keeps_old_actions(old, triggers, gov, acts):
    old_actions = copy.deepcopy(acts.actions)
    new = {**old, "actions": {"unlimited_void": {"keys": "a"}}}
    r = apply_live(old, new, triggers, gov, acts)
    assert acts.actions == old_actions
    assert "actions" not in r.applied
    assert len(r.warnings) == 1 and "unlimited_void" in r.warnings[0]


def test_action_clash_does_not_block_other_settings(old, triggers, gov, acts):
    new = {**old, "hold_frames": 25, "actions": {"unlimited_void": {"keys": "a"}}}
    r = apply_live(old, new, triggers, gov, acts)
    assert r.applied == ["hold_frames"]
    assert all(t.hold_frames == 25 for t in triggers.values())


def test_clash_uses_the_new_domains(old, triggers, gov, acts):
    new = copy.deepcopy(old)
    new["domains"]["wave"] = new["domains"]["unlimited_void"]    # "wave" is only a Domain in new
    new["actions"] = {"wave": {"type": "hi"}}
    r = apply_live(old, new, triggers, gov, acts)
    assert "wave" in r.warnings[0] and "mute" in acts and r.restart == ["domains"]


def test_clash_also_uses_the_running_domains(old, triggers, gov, acts):
    new = copy.deepcopy(old)
    del new["domains"]["idle_death_gamble"]     # still running until restart
    new["actions"] = {**old["actions"], "idle_death_gamble": {"keys": "a"}}
    r = apply_live(old, new, triggers, gov, acts)
    assert "actions" not in r.applied
    assert len(r.warnings) == 1 and "idle_death_gamble" in r.warnings[0]
    assert "idle_death_gamble" not in acts and acts.actions == old["actions"]
    assert r.restart == ["domains"]


def test_restart_only_changes_reported_not_applied(old, triggers, gov, acts):
    new = copy.deepcopy(old)
    new.update(fps=60, camera_index=1)
    new["domains"]["unlimited_void"]["hotkey"] = "<ctrl>+<alt>+x"
    r = apply_live(old, new, triggers, gov, acts)
    assert sorted(r.restart) == ["camera_index", "domains", "fps"]
    assert r.applied == []


def test_result_fields():
    r = LiveResult([], [], [], {}, False)
    assert r.quality_changed is False


# --- ConfigWatcher -----------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def write_cfg(path, cfg, bump=0):
    path.write_text(json.dumps(cfg), encoding="utf-8")
    if bump:
        st = path.stat()
        os.utime(path, (st.st_atime, st.st_mtime + bump))


def make_watcher(tmp_path):
    """A watcher on a valid config.json, with a fake clock; returns (path, clock, watcher)."""
    p = tmp_path / "config.json"
    write_cfg(p, base_cfg())
    clock = FakeClock()
    return p, clock, ConfigWatcher(p, interval_sec=1.0, clock=clock)


def test_watcher_returns_config_once_per_change(tmp_path):
    p, clock, watcher = make_watcher(tmp_path)
    clock.now += 2
    assert watcher.poll() is None                       # nothing changed since start-up
    cfg = base_cfg()
    cfg["hold_frames"] = 20
    write_cfg(p, cfg, bump=5)
    clock.now += 0.5
    assert watcher.poll() is None                       # before the interval
    clock.now += 1
    assert watcher.poll() == cfg                        # after an edit
    clock.now += 2
    assert watcher.poll() is None                       # same file again


def test_watcher_accepts_a_file_saved_with_a_bom(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    cfg = base_cfg()
    cfg["hold_frames"] = 20
    p.write_text(json.dumps(cfg), encoding="utf-8-sig")
    st = p.stat()
    os.utime(p, (st.st_atime, st.st_mtime + 5))
    clock.now += 2
    assert watcher.poll() == cfg
    assert capsys.readouterr().out == ""


def test_watcher_only_stats_after_the_interval(tmp_path, monkeypatch):
    p, clock, watcher = make_watcher(tmp_path)
    calls = []
    real_stat = os.stat
    monkeypatch.setattr(os, "stat", lambda *a, **k: calls.append(a) or real_stat(*a, **k))
    watcher.poll()
    assert calls == []
    clock.now += 1.0
    watcher.poll()
    assert len(calls) == 1


def test_watcher_ignores_half_written_file(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    p.write_text('{"fps": 3', encoding="utf-8")         # truncated JSON
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
    clock.now += 2
    assert watcher.poll() is None
    out = capsys.readouterr().out
    assert out.count("keeping current settings") == 1 and out.startswith("config.json: ")
    clock.now += 2
    assert watcher.poll() is None and capsys.readouterr().out == ""   # same bad file: no repeat


def test_watcher_picks_up_the_fixed_file_after_a_bad_one(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    p.write_text("{", encoding="utf-8")
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
    clock.now += 2
    assert watcher.poll() is None
    capsys.readouterr()
    fixed = base_cfg()
    fixed["fps"] = 24
    write_cfg(p, fixed, bump=10)
    clock.now += 2
    assert watcher.poll() == fixed


def test_invalid_live_values_keep_old_settings(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    cfg = base_cfg()
    cfg["hold_frames"] = 0
    write_cfg(p, cfg, bump=5)
    clock.now += 2
    assert watcher.poll() is None
    out = capsys.readouterr().out
    assert out.count("keeping current settings") == 1
    assert out.startswith("config.json: hold_frames: ")
    clock.now += 2
    assert watcher.poll() is None and capsys.readouterr().out == ""


def test_whole_file_is_validated_not_just_live_keys(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    cfg = base_cfg()
    cfg["fps"] = 0                                      # not a live key, but the file is invalid
    write_cfg(p, cfg, bump=5)
    clock.now += 2
    assert watcher.poll() is None
    assert "config.json: fps: " in capsys.readouterr().out


def test_warning_names_the_first_failing_field(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    cfg = base_cfg()
    cfg["hold_frames"] = 0
    cfg["fps"] = 0
    write_cfg(p, cfg, bump=5)
    clock.now += 2
    watcher.poll()
    first = next(iter(config_store.validate(cfg)))
    assert capsys.readouterr().out.startswith(f"config.json: {first}: ")


def test_watcher_rejects_non_object_json(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    p.write_text("[1, 2]", encoding="utf-8")
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
    clock.now += 2
    assert watcher.poll() is None
    assert capsys.readouterr().out.count("keeping current settings") == 1


def test_watcher_survives_a_missing_file(tmp_path, capsys):
    p, clock, watcher = make_watcher(tmp_path)
    p.unlink()
    clock.now += 2
    assert watcher.poll() is None and capsys.readouterr().out == ""
    cfg = base_cfg()
    cfg["fps"] = 20
    write_cfg(p, cfg, bump=5)
    clock.now += 2
    assert watcher.poll() == cfg
