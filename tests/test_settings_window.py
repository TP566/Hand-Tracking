import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import tkinter as tk

try:
    tk.Tk().destroy()
except tk.TclError:
    pytest.skip("Tk is not available here", allow_module_level=True)

import settings_window
from settings_window import SettingsWindow, launch_settings

REPO = Path(__file__).resolve().parent.parent
REPO_CONFIG = REPO / "config.json"


@pytest.fixture
def cfg_path(tmp_path):
    path = tmp_path / "config.json"
    shutil.copyfile(REPO_CONFIG, path)
    return path


@pytest.fixture
def samples(tmp_path):
    path = tmp_path / "samples"
    path.mkdir()
    return path


@pytest.fixture
def dialogs(monkeypatch):
    """Records every messagebox call; answers come from ``dialogs.answers``."""
    class Dialogs:
        calls: list[tuple[str, str]] = []
        answers: dict[str, object] = {}

    def stub(kind):
        def ask(title=None, message=None, **kw):
            Dialogs.calls.append((kind, message))
            return Dialogs.answers.get(kind)
        return ask

    Dialogs.calls, Dialogs.answers = [], {}
    for kind in ("showerror", "showinfo", "askyesno", "askokcancel", "askyesnocancel"):
        monkeypatch.setattr(settings_window.messagebox, kind, stub(kind))
    return Dialogs


@pytest.fixture
def window(cfg_path, samples, dialogs):
    root = tk.Tk()
    root.withdraw()
    win = SettingsWindow(root, cfg_path, samples)
    yield win
    root.destroy()


def on_disk(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_round_trip_without_changes(window, cfg_path):
    assert window.collect() == on_disk(cfg_path)


def test_round_trip_keeps_json_types_and_unknown_keys(tmp_path, samples, dialogs):
    path = tmp_path / "config.json"
    cfg = on_disk(REPO_CONFIG)
    cfg["my_key"] = {"x": 1}
    cfg["domains"]["idle_death_gamble"]["extra"] = 7
    cfg["domains"]["idle_death_gamble"]["loop_end_sec"] = 20.0
    path.write_text(json.dumps(cfg), encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    try:
        collected = SettingsWindow(root, path, samples).collect()
    finally:
        root.destroy()
    assert collected == cfg
    assert json.dumps(collected) == json.dumps(cfg)     # 0.0 stays 0.0, 12 stays 12


def test_edit_and_save_writes_config(window, cfg_path):
    window.fields["hold_frames"].set("20")
    window.fields["cooldown_sec"].set("2")
    assert window.save()
    saved = on_disk(cfg_path)
    assert saved["hold_frames"] == 20 and isinstance(saved["hold_frames"], int)
    assert saved["cooldown_sec"] == 2.0 and isinstance(saved["cooldown_sec"], float)
    assert window.status.get() == "Saved. Live settings applied."


def test_restart_only_change_is_reported(window, cfg_path):
    window.fields["camera_index"].set("1")
    window.domains["idle_death_gamble"]["hotkey"].set("<ctrl>+<alt>+g")
    assert window.save()
    assert window.status.get() == "Saved. Restart the app to apply: camera_index, domains"


def test_invalid_value_blocks_save_and_shows_error(window, cfg_path):
    before = cfg_path.read_bytes()
    window.fields["hold_frames"].set("0")
    assert not window.save()
    assert window.errors["hold_frames"]
    assert window.error_vars["hold_frames"].get() == window.errors["hold_frames"]
    assert cfg_path.read_bytes() == before
    window.fields["hold_frames"].set("12")
    assert window.save()
    assert window.errors == {} and window.error_vars["hold_frames"].get() == ""


def test_unconvertible_entry_is_reported_not_crashed(window, cfg_path):
    window.fields["hold_frames"].set("abc")
    window.domains["idle_death_gamble"]["loop_start_sec"].set("soon")
    assert window.collect()["hold_frames"] == "abc"
    assert not window.save()
    assert window.errors["hold_frames"] == "Must be a whole number."
    assert "domains.idle_death_gamble.loop_start_sec" in window.errors
    assert window.error_vars["domains.idle_death_gamble.loop_start_sec"].get()


def test_domain_fields_convert(window):
    vars_ = window.domains["idle_death_gamble"]
    vars_["loop_end_sec"].set("12.5")
    vars_["keywords"].set(" hakari ,  jackpot,, ")
    domain = window.collect()["domains"]["idle_death_gamble"]
    assert domain["loop_end_sec"] == 12.5
    assert domain["keywords"] == ["hakari", "jackpot"]
    vars_["loop_end_sec"].set("  ")
    assert window.collect()["domains"]["idle_death_gamble"]["loop_end_sec"] is None


def test_hold_frames_shows_seconds(window):
    window.fields["hold_frames"].set("15")
    assert window.hold_seconds.get() == "≈ 0.5 s"
    window.fields["hold_frames"].set("x")
    assert window.hold_seconds.get() == ""


def test_add_and_remove_domain(window, cfg_path, dialogs):
    assert window.add_domain("chimera")
    assert "chimera" in window.collect()["domains"]
    assert "teach.bat chimera" in window.status.get()
    window.remove_domain("chimera")
    assert "chimera" not in window.collect()["domains"]


def test_add_domain_refuses_bad_or_used_names(window, dialogs):
    assert not window.add_domain("bad name")
    assert not window.add_domain("idle_death_gamble")
    assert not window.add_domain("mute")
    assert not window.add_domain("none")
    assert len([c for c in dialogs.calls if c[0] == "showerror"]) == 4
    assert list(window.collect()["domains"]) == list(on_disk(REPO_CONFIG)["domains"])


def test_new_domain_needs_hotkey_before_saving(window, cfg_path):
    window.add_domain("chimera")
    assert not window.save()
    assert "domains.chimera.hotkey" in window.errors
    window.domains["chimera"]["hotkey"].set("<ctrl>+<alt>+c")
    assert window.save()
    assert on_disk(cfg_path)["domains"]["chimera"]["hotkey"] == "<ctrl>+<alt>+c"


def test_rename_domain_moves_samples(window, cfg_path, samples):
    (samples / "idle_death_gamble").mkdir()
    (samples / "idle_death_gamble" / "x.json").write_text("{}")
    assert window.rename("domain", "idle_death_gamble", "hakari_gamble")
    assert (samples / "hakari_gamble" / "x.json").exists()
    assert not (samples / "idle_death_gamble").exists()
    assert list(on_disk(cfg_path)["domains"])[-1] == "hakari_gamble"
    assert "hakari_gamble" in window.domains and "idle_death_gamble" not in window.domains
    assert "restart" in window.status.get().lower()


def test_rename_with_unsaved_edits_saves_first(window, cfg_path, dialogs):
    window.fields["hold_frames"].set("20")
    dialogs.answers["askokcancel"] = True
    assert window.rename("action", "mute", "silence")
    saved = on_disk(cfg_path)
    assert saved["hold_frames"] == 20
    assert "silence" in saved["actions"] and "mute" not in saved["actions"]


def test_rename_cancelled_changes_nothing(window, cfg_path, dialogs):
    before = cfg_path.read_bytes()
    window.fields["hold_frames"].set("20")
    dialogs.answers["askokcancel"] = False
    assert not window.rename("action", "mute", "silence")
    assert cfg_path.read_bytes() == before
    assert window.fields["hold_frames"].get() == "20"


def test_rename_error_is_shown_verbatim(window, dialogs):
    assert not window.rename("domain", "unlimited_void", "gojo")
    assert dialogs.calls[-1] == ("showerror", "unlimited_void is a built-in sign and cannot be renamed.")


def test_built_in_domains_have_no_rename_button(window):
    assert "unlimited_void" not in window.rename_buttons
    assert "malevolent_shrine" not in window.rename_buttons
    assert "idle_death_gamble" in window.rename_buttons


def test_actions_round_trip_and_add(window, cfg_path, samples):
    window.add_action("fist", "type", "gg")
    assert window.collect()["actions"]["fist"] == {"type": "gg"}
    combo = window.action_rows[-1].sign_box
    known = settings_window.config_store.known_signs
    assert list(combo.cget("values")) == known(on_disk(cfg_path), samples)
    (samples / "fist").mkdir()                    # taught while the window is open
    window.root.tk.call(combo.cget("postcommand"))
    assert list(combo.cget("values")) == known(on_disk(cfg_path), samples)
    assert "fist" in combo.cget("values")
    assert window.save()
    assert on_disk(cfg_path)["actions"]["fist"] == {"type": "gg"}


def test_save_after_external_change_offers_reload(window, cfg_path, dialogs):
    stamp = cfg_path.stat().st_mtime + 5
    os.utime(cfg_path, (stamp, stamp))
    before = cfg_path.read_bytes()
    window.fields["hold_frames"].set("20")
    dialogs.answers["askyesno"] = False
    assert not window.save()
    assert cfg_path.read_bytes() == before
    assert dialogs.calls[-1] == ("askyesno", "config.json was changed outside this window. "
                                 "Reload it? (Your unsaved edits will be lost)")
    assert window.fields["hold_frames"].get() == "20"


def test_reload_after_external_change(window, cfg_path, dialogs):
    cfg = on_disk(cfg_path)
    cfg["hold_frames"] = 30
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    stamp = cfg_path.stat().st_mtime + 5
    os.utime(cfg_path, (stamp, stamp))
    window.fields["hold_frames"].set("20")
    dialogs.answers["askyesno"] = True
    assert not window.save()
    assert window.fields["hold_frames"].get() == "30"
    window.fields["hold_frames"].set("25")
    assert window.save()
    assert on_disk(cfg_path)["hold_frames"] == 25


def test_close_asks_only_when_there_are_edits(tmp_path, samples, dialogs):
    path = tmp_path / "config.json"
    cfg = on_disk(REPO_CONFIG)
    del cfg["miss_tolerance"], cfg["quality"]          # filled with defaults, not an edit
    path.write_text(json.dumps(cfg), encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    win = SettingsWindow(root, path, samples)
    win.fields["hold_frames"].set("20")
    dialogs.answers["askyesnocancel"] = None             # Cancel: stay open
    win._on_close()
    assert root.winfo_exists() and dialogs.calls[-1][0] == "askyesnocancel"
    win.fields["hold_frames"].set("12")
    dialogs.calls.clear()
    win._on_close()
    assert dialogs.calls == []
    assert on_disk(path) == cfg


def test_start_button_follows_app_lock(window, monkeypatch):
    monkeypatch.setattr(settings_window, "app_running", lambda path: True)
    window.refresh_start()
    assert str(window.start_button.cget("state")) == "disabled"
    monkeypatch.setattr(settings_window, "app_running", lambda path: False)
    window.refresh_start()
    assert str(window.start_button.cget("state")) == "normal"


def test_video_path_relative_inside_project(tmp_path):
    inside = settings_window.ROOT / "videos" / "a.mp4"
    assert settings_window.video_value(str(inside)) == "videos/a.mp4"
    outside = tmp_path / "b.mp4"
    assert settings_window.video_value(str(outside)) == str(outside)


def test_launch_settings_starts_own_process(monkeypatch):
    calls = []
    monkeypatch.setattr(settings_window.subprocess, "Popen",
                        lambda args, **kw: calls.append((args, kw)))
    launch_settings()
    args, kw = calls[0]
    assert args == [sys.executable, str(Path(settings_window.__file__).resolve())]
    assert kw["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
