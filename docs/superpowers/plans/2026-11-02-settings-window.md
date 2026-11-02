# Settings Window and Tray Icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A settings window that covers all of `config.json` (with Domain add/remove/rename), sign sensitivity, performance and actions that apply live to the running app, and a tray icon.

**Architecture:**
- **Settings logic:** a GUI-free model (`config_store.py`) handles loading, validating, saving atomically and renaming signs.
- **Settings window:** a Tkinter window (`settings_window.py`), run as its own process, edits `config.json` through that model.
- **Running app:** polls the file (`live_config.py`) and applies the live groups to the existing `HoldTrigger`s, the `QualityGovernor`, the preview options and the `Actions`.
- **Tray icon:** `tray.py`, using pystray, opens the window and quits the app.
- **Single-instance check:** `instance.py`, so "Start app" knows whether the app is already running.

**Tech Stack:** Python 3.14, Tkinter/ttk (standard library), pystray + Pillow (new), pynput (existing, for hotkey parsing), pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-settings-window-design.md`

## Global Constraints
- Windows only; run tests with `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp <scratch dir>`, since the sandbox blocks the default temp folder.
- New dependencies: `pystray` and `pillow` only.
- The settings window runs as a **separate process**; Tkinter never runs inside `main.py`.
- Writes to `config.json` are atomic (temp file + `os.replace`), and the previous file is kept as `config.json.bak`.
- Unknown keys in `config.json` are preserved on save.
- Sign names match `learned_signs.SIGN_NAME` (`^[A-Za-z0-9_]+$`).
- Built-in signs (`hand_signs.GESTURES` keys: `unlimited_void`, `malevolent_shrine`) can never be renamed.
- Live groups: `hold_frames`, `miss_tolerance`, `cooldown_sec`, `quality`, `show_preview`, `preview_width`, `mirror_preview`, `actions`. Everything else is restart-only.
- A bad or half-written `config.json` never crashes the running app: it keeps the current settings and prints one warning per change.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Pass multi-line messages with `git commit -F <file>`, because PowerShell 5.1 breaks embedded quotes.

## Review Focus
1. **The window saves while the app is reading:** the app must never see a partial file (atomic save), and a partial hand-edited file must be ignored with one warning. Tested in Task 1 (`test_save_is_atomic_and_keeps_backup`) and Task 3 (`test_watcher_ignores_half_written_file`).
2. **A hand edit sets an invalid value** (`"hold_frames": 0` or `"abc"`): the app keeps its old value and warns. Tested in Task 3 (`test_invalid_live_values_keep_old_settings`).
3. **Rename while `teach.bat` holds the folder open:** the folder move fails, nothing is saved, and the config is unchanged. Tested in Task 2 (`test_rename_rolls_back_when_folder_move_fails`).
4. **`config.json` changed on disk while the window is open** (a hand edit or a second window): saving must not silently overwrite it; the window offers to reload. Tested in Task 1 (`test_save_refuses_when_file_changed_since_load`).
5. **An older config without `actions` or `title` keys:** the window and the validation treat missing sections as empty or defaults. Tested in Task 1 (`test_validate_accepts_config_without_optional_sections`).

---

### Task 1: Config model: load, validate, save

**Files:**
- Create: `config_store.py`
- Test: `tests/test_config_store.py`

**Interfaces:**
- Produces:
  - `load(path: Path) -> tuple[dict, float]`: config plus the file's mtime at load.
  - `save(path: Path, cfg: dict, loaded_mtime: float | None = None) -> float`: atomic write, then `.bak`; raises `ConfigChanged` if `loaded_mtime` is given and the file's mtime differs; returns the new mtime.
  - `class ConfigChanged(Exception)`
  - `validate(cfg: dict) -> dict[str, str]`: field path → message, empty when valid. Paths look like `"hold_frames"`, `"domains.<name>.hotkey"`, `"actions.<name>"`.
  - `known_signs(cfg: dict, samples_dir: Path) -> list[str]`: sorted union of `GESTURES` keys, Domain names and `samples/` label folders (excluding `none`).
  - `RANGES: dict[str, tuple[float, float]]`: the numeric limits below.
  - `LIVE_KEYS: tuple[str, ...]`: the live-group keys from the Global Constraints.

- [ ] **Step 1: Write the failing tests**

```python
def test_save_is_atomic_and_keeps_backup(tmp_path):
    p = tmp_path / "config.json"; p.write_text('{"fps": 30}', encoding="utf-8")
    cfg, mtime = load(p)
    cfg["fps"] = 25
    save(p, cfg, mtime)
    assert json.loads(p.read_text())["fps"] == 25
    assert json.loads((tmp_path / "config.json.bak").read_text())["fps"] == 30
    assert not list(tmp_path.glob("*.tmp"))

def test_save_preserves_unknown_keys(tmp_path): ...       # {"my_key": 1} survives load→save
def test_save_refuses_when_file_changed_since_load(tmp_path):
    # load, then write the file again (os.utime to a different mtime), save(..., mtime) raises ConfigChanged
def test_validate_reports_each_bad_field():
    cfg = valid_cfg(); cfg["hold_frames"] = 0; cfg["quality"] = "ultra"
    cfg["domains"]["idle_death_gamble"]["hotkey"] = "<ctrl>+<nope>"
    cfg["actions"] = {"mute": {}, "unlimited_void": {"keys": "a"}, "bad name!": {"keys": "a"}}
    errors = validate(cfg)
    assert set(errors) >= {"hold_frames", "quality", "domains.idle_death_gamble.hotkey",
                           "actions.mute", "actions.unlimited_void", "actions.bad name!"}
def test_validate_rejects_duplicate_hotkeys(): ...         # two Domains with "<ctrl>+<alt>+d" → both paths reported
def test_validate_rejects_loop_end_before_start(): ...     # loop_end_sec 2.0 with loop_start_sec 3.0
def test_validate_accepts_config_without_optional_sections():
    cfg = valid_cfg(); cfg.pop("actions"); cfg["domains"]["unlimited_void"].pop("title", None)
    assert validate(cfg) == {}
def test_validate_accepts_repo_config():                   # the committed config.json validates cleanly
def test_known_signs_includes_taught_folders(tmp_path):    # samples/mute/*.json → "mute" listed; "none" not
```
`valid_cfg()` is a test helper that returns a deep copy of the repo's `config.json`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config_store.py -q -p no:cacheprovider --basetemp <scratch>\pt`
Expected: FAIL with `ModuleNotFoundError: config_store`

- [ ] **Step 3: Implement `config_store.py`**
- `RANGES`: `camera_index (0, 10)`, `width (160, 3840)`, `height (120, 2160)`, `camera_fps (1, 120)`, `fps (1, 60)`, `hold_frames (1, 120)`, `miss_tolerance (0, 30)`, `cooldown_sec (0, 10)`, `preview_width (160, 1920)`. `hold_frames`, `miss_tolerance`, `camera_index`, `width`, `height` and `fps` must be integers.
- `quality` ∈ `{"auto", "high", "low"}`; booleans are required for `show_preview` and `mirror_preview`.
- Domains: `loop_start_sec ≥ 0`; `loop_end_sec` is `null` or greater than `loop_start_sec`; `keywords` is a list of strings; hotkeys must pass `pynput.keyboard.HotKey.parse` and be unique across Domains.
- Actions: reuse `actions.validate` semantics. Exactly one of `keys`/`type`/`open` with a non-empty string; the name matches `SIGN_NAME`; the name isn't a Domain.
- `save`: write `path.with_suffix(".json.tmp")`, `shutil.copy2(path, ".bak")` if `path` exists, then `os.replace(tmp, path)`. Use `json.dumps(cfg, indent=2)` plus a trailing newline.

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2. Expected: all PASS.

- [ ] **Step 5: Commit**: `config_store.py`, `tests/test_config_store.py`. Message: "Add config model with validation and atomic save".

---

### Task 2: Renaming signs with their recordings

**Files:**
- Modify: `config_store.py`
- Test: `tests/test_config_store.py`

**Interfaces:**
- Consumes: `load`, `save`, `validate`, `ConfigChanged` (Task 1).
- Produces:
  - `rename_sign(cfg: dict, kind: str, old: str, new: str, config_path: Path, samples_dir: Path, loaded_mtime: float | None = None) -> tuple[dict, float]`: `kind` is `"domain"` or `"action"`. It returns the saved config and the new mtime. On refusal or failure it raises `RenameError(message)`, and both disk and `cfg` are left unchanged.
  - `class RenameError(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
def test_rename_domain_moves_recordings_and_config(tmp_path):
    # config with domain "hakari", samples/hakari/a.json
    cfg2, _ = rename_sign(cfg, "domain", "hakari", "gamble", cfg_path, samples)
    assert "gamble" in cfg2["domains"] and "hakari" not in cfg2["domains"]
    assert list(cfg2["domains"]) == expected_order_with_gamble_in_hakari_slot
    assert (samples / "gamble" / "a.json").exists() and not (samples / "hakari").exists()
    assert json.loads(cfg_path.read_text())["domains"]["gamble"]["hotkey"] == old_hotkey
def test_rename_action_moves_recordings(tmp_path): ...            # actions "mute" → "silence"
def test_rename_without_recordings_folder(tmp_path): ...          # only the config changes
def test_rename_refuses_builtin_sign(tmp_path):
    with pytest.raises(RenameError, match="built-in"):
        rename_sign(cfg, "domain", "unlimited_void", "void", cfg_path, samples)
def test_rename_refuses_taken_or_invalid_names(tmp_path):         # existing Domain, action, samples/<new>, "bad name!"
def test_rename_rolls_back_when_folder_move_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store.os, "replace", raise_permission_error_for_folders)
    with pytest.raises(RenameError, match="in use"):
        rename_sign(...)
    assert cfg_path.read_text() == original_text and (samples / "hakari").exists()
def test_rename_rolls_back_folder_when_save_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "save", raise_oserror)
    with pytest.raises(RenameError): rename_sign(...)
    assert (samples / "hakari").exists() and not (samples / "gamble").exists()
```

- [ ] **Step 2: Run tests to verify they fail**: `-k rename`. Expected: FAIL (`rename_sign` not defined).

- [ ] **Step 3: Implement `rename_sign`**
- Work on a deep copy, rebuilding the dict so the renamed key keeps its position.
- Order: validate the name and refusals → move the folder with `os.replace` (a `PermissionError` becomes `RenameError("…the recordings folder is in use, close teach.bat/record.bat and try again")`) → `save`.
- On a save failure, move the folder back and raise `RenameError`.

- [ ] **Step 4: Run tests to verify they pass**: `tests/test_config_store.py`. Expected: all PASS.

- [ ] **Step 5: Commit**: message "Rename signs together with their recordings".

---

### Task 3: Live config in the running app (logic)

**Files:**
- Create: `live_config.py`
- Modify: `pipeline.py` (`QualityGovernor.set_mode`)
- Test: `tests/test_live_config.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes:
  - `config_store.validate`, `config_store.LIVE_KEYS` (Task 1)
  - `actions.validate`, `actions.Actions` (existing)
  - `HoldTrigger` attributes `hold_frames`, `miss_tolerance`, `cooldown_sec` (existing)
- Produces:
  - `QualityGovernor.set_mode(mode: str) -> bool`: `"high"` sets level 0, `"low"` sets the last level, and `"auto"` keeps the level. Returns True when the level changed.
  - `class ConfigWatcher(path: Path, interval_sec: float = 1.0, clock=time.monotonic)` with `poll() -> dict | None`. It returns the parsed config when the mtime changed and the file parses and validates; otherwise None. It prints one warning per failed change (`"config.json: <reason>; keeping current settings"`).
  - `@dataclass LiveResult(applied: list[str], restart: list[str], warnings: list[str], preview: dict, quality_changed: bool)`
  - `apply_live(old: dict, new: dict, triggers: dict[str, HoldTrigger], governor: QualityGovernor, actions: Actions) -> LiveResult`. It mutates the triggers, the governor and `actions.actions`. `preview` holds the new `show_preview`, `preview_width` and `mirror_preview` values. `restart` lists the top-level keys outside `LIVE_KEYS` whose values differ, with `"domains"` as one entry.

- [ ] **Step 1: Write the failing tests**

```python
def test_governor_set_mode():                       # in test_pipeline.py
    gov = QualityGovernor("auto"); gov.level = 2
    assert gov.set_mode("high") and gov.level == 0 and gov.mode == "high"
    assert gov.set_mode("low") and gov.level == len(QUALITY_LEVELS) - 1
    assert not gov.set_mode("auto") and gov.level == len(QUALITY_LEVELS) - 1

def test_sensitivity_applied_to_all_triggers():
    new = {**old, "hold_frames": 20, "miss_tolerance": 5, "cooldown_sec": 3.0}
    r = apply_live(old, new, triggers, gov, acts)
    assert all((t.hold_frames, t.miss_tolerance, t.cooldown_sec) == (20, 5, 3.0) for t in triggers.values())
    assert "hold_frames" in r.applied and r.restart == []
def test_quality_and_preview_applied(): ...        # quality "high" → quality_changed True; preview dict has the new values
def test_actions_swapped(): ...                    # new action "deafen" present in acts.actions after apply
def test_action_clash_keeps_old_actions():
    new["actions"] = {"unlimited_void": {"keys": "a"}}
    r = apply_live(old, new, triggers, gov, acts)
    assert acts.actions == old_actions and r.warnings
def test_restart_only_changes_reported_not_applied():
    new = {**old, "fps": 60, "camera_index": 1, "domains": changed_domains}
    assert set(apply_live(...).restart) == {"fps", "camera_index", "domains"}
def test_watcher_returns_config_once_per_change(tmp_path): ...   # fake clock; poll None before interval, dict after an edit, None again
def test_watcher_ignores_half_written_file(tmp_path, capsys):
    p.write_text('{"fps": 3', encoding="utf-8")   # truncated JSON
    assert watcher.poll() is None and capsys.readouterr().out.count("keeping current settings") == 1
    assert watcher.poll() is None and capsys.readouterr().out == ""   # same bad file: no repeat warning
def test_invalid_live_values_keep_old_settings(tmp_path): ...    # "hold_frames": 0 → poll None, one warning
```

- [ ] **Step 2: Run tests to verify they fail.** Expected: FAIL (module and method missing).

- [ ] **Step 3: Implement `set_mode` in `pipeline.py` and `live_config.py`.** `ConfigWatcher` checks `os.stat(path).st_mtime` only when `clock() - last_check >= interval_sec`.

- [ ] **Step 4: Run** `tests/test_live_config.py tests/test_pipeline.py`. Expected: all PASS.

- [ ] **Step 5: Commit**: message "Apply live settings from config.json changes".

---

### Task 4: Single-instance lock and tray icon

**Files:**
- Create: `instance.py`, `tray.py`
- Modify: `requirements.txt` (add `pystray`, `pillow`)
- Test: `tests/test_instance.py`, `tests/test_tray.py`

**Interfaces:**
- Produces:
  - `instance.hold_app_lock(path: Path) -> AppLock`: an object with `.release()`, holding an exclusive `msvcrt.locking` lock on the file.
  - `instance.app_running(path: Path) -> bool`: True while another process (or `AppLock`) holds the lock.
  - `LOCK_PATH = ROOT / ".app.lock"`, added to `.gitignore`.
  - `tray.make_icon_image(size: int = 64) -> PIL.Image.Image`
  - `tray.build_menu(on_settings: Callable[[], None], on_quit: Callable[[], None]) -> pystray.Menu`, with items titled exactly `"Settings"` and `"Quit"`.
  - `tray.start_tray(on_settings, on_quit) -> pystray.Icon`: started with `run_detached()`; the caller calls `.stop()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_lock_reports_running_until_released(tmp_path):
    p = tmp_path / ".app.lock"
    assert not app_running(p)
    lock = hold_app_lock(p); assert app_running(p)
    lock.release(); assert not app_running(p)

def test_icon_image_size():
    assert make_icon_image(64).size == (64, 64)
def test_menu_items_call_handlers():
    calls = []
    menu = build_menu(lambda: calls.append("s"), lambda: calls.append("q"))
    items = {i.text: i for i in menu.items}
    assert set(items) == {"Settings", "Quit"}
    items["Settings"](None); items["Quit"](None)      # pystray MenuItem is callable with the icon
    assert calls == ["s", "q"]
```

- [ ] **Step 2: Install the new dependencies and run tests to verify they fail**
- `.venv\Scripts\python.exe -m pip install pystray pillow`
- Run the tests. Expected: FAIL (modules missing).

- [ ] **Step 3: Implement `instance.py` and `tray.py`.** The icon is a purple disc with a white ring, drawn with `PIL.ImageDraw`.

- [ ] **Step 4: Run the tests.** Expected: PASS.

- [ ] **Step 5: Commit** `instance.py`, `tray.py`, the tests, `requirements.txt` and `.gitignore`. Message: "Add tray icon and single-instance lock".

---

### Task 5: Settings window

**Files:**
- Create: `settings_window.py`, `settings.bat` (CRLF, same structure as `record.bat`, running `settings_window.py`)
- Test: `tests/test_settings_window.py`

**Interfaces:**
- Consumes:
  - `config_store.load`, `save`, `validate`, `known_signs`, `rename_sign`, `ConfigChanged`, `RenameError`, `LIVE_KEYS` (Tasks 1–2)
  - `instance.app_running`, `instance.LOCK_PATH` (Task 4)
- Produces:
  - `launch_settings() -> None`: starts `settings_window.py` in a new process via `subprocess.Popen([sys.executable, str(path)], creationflags=CREATE_NEW_PROCESS_GROUP)`. It returns immediately. Used by the tray in Task 6.
  - `class SettingsWindow(root: tk.Tk, config_path: Path, samples_dir: Path)` with:
    - `collect() -> dict`: the config built from the widgets
    - `save() -> bool`: validates, writes, and shows status or errors
    - `add_domain(name: str)`, `remove_domain(name: str)`, `rename(kind: str, old: str, new: str)`
    - `fields: dict[str, tk.Variable]`: top-level settings keyed like `config_store.validate` paths
    - `errors: dict[str, str]`: messages from the last `save()`, keyed the same way and shown next to each field

- [ ] **Step 1: Write the failing tests** (skip the module when `tk.Tk()` raises `TclError`)

```python
def test_round_trip_without_changes(tmp_path, window):   # window fixture: repo config copied to tmp, root withdrawn
    assert window.collect() == json.loads(cfg_path.read_text())
def test_edit_and_save_writes_config(tmp_path, window):
    window.fields["hold_frames"].set("20"); assert window.save()
    assert json.loads(cfg_path.read_text())["hold_frames"] == 20
def test_invalid_value_blocks_save_and_shows_error(window):
    window.fields["hold_frames"].set("0"); assert not window.save()
    assert window.errors["hold_frames"]          # message shown next to the field
def test_add_and_remove_domain(window): ...       # add "chimera" → in collect(); remove → gone
def test_rename_domain_moves_samples(window): ... # samples/idle_death_gamble/x.json follows to the new name
def test_save_after_external_change_offers_reload(window, monkeypatch):
    # touch the file with a new mtime; stub messagebox.askyesno → False; save() returns False, the file is untouched
```

- [ ] **Step 2: Run tests to verify they fail.** Expected: FAIL (module missing).

- [ ] **Step 3: Implement `settings_window.py`**
- Use `ttk.Notebook` tabs: General / Signs / Domains / Actions.
- Section headers say exactly **"Live"** or **"Applies on restart"**.
- The Signs tab shows `≈ {hold_frames / 30:.1f} s` next to the hold frames field.
- The Actions sign field is a `ttk.Combobox` filled with `known_signs`.
- The buttons are **Save** and **Start app**. Start app is disabled while `app_running(LOCK_PATH)` is true, re-checked every 2 s.
- After saving, show "Saved. Live settings applied." or "Saved. Restart the app to apply: <keys>".
- On `ConfigChanged`, ask "config.json was changed outside this window. Reload it? (Your unsaved edits will be lost)".

- [ ] **Step 4: Run the tests.** Expected: PASS. Then run `settings.bat` by hand: the window opens with the current values.

- [ ] **Step 5: Commit** `settings_window.py`, `settings.bat` and the test. Message: "Add settings window".

---

### Task 6: Wire live config, tray and lock into the app

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes:
  - `ConfigWatcher`, `apply_live`, `LiveResult` (Task 3)
  - `hold_app_lock`, `LOCK_PATH` (Task 4)
  - `start_tray` (Task 4)
  - `launch_settings` (Task 5)
- Produces: nothing new for other tasks.

- [ ] **Step 1: Integrate**
- Hold `hold_app_lock(LOCK_PATH)` for the whole of `main()` and release it in `finally`.
- Start the tray with `on_settings=launch_settings` and `on_quit=lambda: post("__quit__")`. The loop breaks on `"__quit__"` before Domain dispatch.
- Create `ConfigWatcher(ROOT / "config.json")`. When `poll()` returns a config, call `apply_live(cfg, new, triggers, governor, actions)`, then:
  - `cfg.update(result.preview)`
  - recompute `preview_w` and `preview_scale`
  - when `show_preview` becomes false, call `cv2.destroyWindow("Domain Expansion (preview)")`
  - if `quality_changed`, set `blend_size = apply_quality(governor.level)`
  - recompute `bars`
  - print `applied` and `warnings`, plus `"saved; restart the app to apply: …"` for `restart`
  - set `cfg` for the live keys only, so restart-only values keep reflecting what's running.
- When the preview is off, still pump `cv2.waitKey(1)` only if a window exists. Quitting then works through the tray.

- [ ] **Step 2: Run the full suite.** Expected: all PASS.

- [ ] **Step 3: Headless check**
- Copy the scratchpad `bench.py` to `bench_live.py`. At 4 s, rewrite `config.json` with `hold_frames` 20 and a new action. At 8 s, post `"__quit__"`.
- Assert: every trigger has `hold_frames == 20`; the new action is in `actions.actions`; output fps in the 4–8 s window is within 1 fps of the 0–4 s window; the run ends cleanly before `END_AT`.
- Restore `config.json` afterwards.

- [ ] **Step 4: Commit** `main.py`. Message: "Apply settings live and add tray icon to the app".

---

### Task 7: Docs and release

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README**
- Add a "Settings window" section after Step 5: `settings.bat`, the tabs, Live versus Applies on restart, the tray icon (*Settings*, *Quit*), and rename moving the recordings.
- Replace "Open `config.json` with Notepad…" with "Use the settings window (or edit `config.json` by hand)".
- Change "Add your own Domain" to use **Add Domain**.
- Add `settings.bat` to the developer file list if there is one.

- [ ] **Step 2: Run the full suite, then a fresh-clone check**
- Run the full suite.
- Clone into the scratchpad, run `setup.bat` (it installs pystray and Pillow), then `settings.bat`: the window opens.

- [ ] **Step 3: Commit, fast-forward `main`, and push** `main` and `feat/settings-window`.
