import json
import os
import subprocess
import sys
from pathlib import Path

import main

FIXTURE_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config.json"


# --- tray -------------------------------------------------------------------------------

def test_without_pystray_the_app_runs_without_a_tray(monkeypatch, capsys):
    monkeypatch.setattr(main, "start_tray", None)
    assert main.open_tray(on_quit=lambda: None) is None
    assert capsys.readouterr().out == main.TRAY_MISSING + "\n"


def test_a_tray_that_fails_to_start_is_skipped(monkeypatch, capsys):
    def broken(**kwargs):
        raise OSError("no notification area")

    monkeypatch.setattr(main, "start_tray", broken)
    assert main.open_tray(on_quit=lambda: None) is None
    assert "no notification area" in capsys.readouterr().out


def test_tray_gets_settings_and_quit(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "start_tray", lambda **kwargs: calls.append(kwargs) or "icon")
    quit_ = lambda: None
    assert main.open_tray(on_quit=quit_) == "icon"
    assert calls == [{"on_settings": main.launch_settings, "on_quit": quit_}]


def test_main_imports_without_pystray():
    # A fresh interpreter: an older install's .venv has no pystray until setup.bat runs again.
    code = ("import sys; sys.modules['pystray'] = None; import main; "
            "assert main.start_tray is None; main.open_tray(lambda: None)")
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(main.__file__).parent,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == main.TRAY_MISSING


# --- config -----------------------------------------------------------------------------

def test_load_config_accepts_a_bom(monkeypatch, tmp_path):
    (tmp_path / "config.json").write_text('{"fps": 30}', encoding="utf-8-sig")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    assert main.load_config() == {"fps": 30}


def test_save_during_startup_is_picked_up(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(FIXTURE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["hold_frames"] = 20

    class Lock:
        def release(self):
            pass

    def slow_startup():
        # The settings window saves while the app is still loading.
        path.write_text(json.dumps(saved), encoding="utf-8")
        st = path.stat()
        os.utime(path, (st.st_atime, st.st_mtime + 5))
        return Lock()

    seen = []

    def fake_run(cfg, show_stats, watcher):
        watcher.interval = 0
        seen.append((cfg["hold_frames"], watcher.poll()))

    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "take_app_lock", slow_startup)
    monkeypatch.setattr(main, "run", fake_run)
    main.main()
    assert seen == [(12, saved)]
