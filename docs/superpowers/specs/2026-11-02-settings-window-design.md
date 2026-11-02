# Design: Settings window and tray icon (live settings)

Approved 2026-11-02.

## Intent and why
The user (the app's owner, running it on their laptop for Discord calls) finds editing `config.json` in Notepad the most fiddly part of using the app. They change settings both **before starting** and **mid-call**. The settings they want to tweak live are:
- sign sensitivity
- performance
- PC actions

Success means they never have to open `config.json` again, and they can adjust those three areas during a call without restarting the camera.

## Goals
- A settings window covering everything in `config.json`: general/camera, signs, Domains and actions.
- Settings in the live groups apply to the **running** app within about a second of saving, with no restart.
- Settings that can't change live (camera, resolution, output fps, Domains) are clearly marked **"applies on restart"**.
- The window can be opened before launch (`settings.bat`) and while the app runs (tray icon).
- A tray icon for the running app, with *Settings* and *Quit*.

## Non-goals (this round)
- Friends installing without Python (the `.exe`; a later item).
- The visual loop-point picker (a later item; the Domains tab leaves room for a button).
- Teaching signs from the window (that stays `teach.bat`).
- Live changes to the camera, resolution, output fps or Domain videos.

## Anti-goals (a failure even if it "works")
- A bad or half-written edit crashes the app or interrupts the call.
- The user's config gets lost or corrupted.
- Hand-editing `config.json` stops working.
- The app gets noticeably slower.

## Constraints
- Windows. Python 3.14 in `.venv`. The existing stack: OpenCV preview window, pynput hotkeys, threaded pipeline (`pipeline.py`).
- Tkinter and OpenCV's `imshow` both want the main thread, so the settings window runs as a **separate process**.
- Only one new dependency is allowed: `pystray`, plus Pillow, which it needs. Tkinter ships with Python.

## Approaches considered
- **A. Separate Tkinter settings window that edits `config.json`; the app watches the file and applies live settings. Chosen by the user.** It keeps the GUI out of the camera loop's process, needs no new UI framework, and hand-editing still works.
- **B. A settings web page served by the app.** Prettier, but it adds a web server, and before launch something would still have to start that server.
- **C. Sliders in the OpenCV preview.** Can't edit text (action keys, typed text), and clutters the preview.

## How it works (decided)

### Settings window (new `settings_window.py`, `settings.bat`)
- A Tkinter window with tabs:
  - **General:** camera index, width/height, camera fps, output fps, quality (auto/high/low), show preview, preview width, mirror preview.
  - **Signs:** hold frames (with the matching seconds shown next to it: frames Ã· 30), miss tolerance, cooldown.
  - **Domains:** one section per Domain: title, video (text + Browseâ€¦), keywords, loop start/end, hotkey.
    - **Add Domain** asks for a sign name (letters, digits and `_`). The name must be unique among Domains and actions.
    - **Remove** deletes a Domain after a confirmation.
    - **Rename** changes a Domain's sign name **and moves its recordings** (`samples/<old>` â†’ `samples/<new>`), so a taught sign keeps working without re-teaching (decided with the user). Details are under *Renaming signs* below.
    - A new Domain gets a hint to teach its sign with `teach.bat <name>`.
  - **Actions:** one row per action: sign name, action type (keys/type/open), value. Add and remove rows. Changing an existing row's sign name is a **rename** and follows the same rules as Domains.
- Each section is labelled **Live** or **Applies on restart**.
- **Save** writes the config. A **Start app** button starts `main.py` in its own console when the app isn't already running.
- Inputs are validated before saving, with the problem shown next to the field:
  - numbers in range
  - sign names: letters, digits and `_` (same rule as `learned_signs.SIGN_NAME`)
  - exactly one value per action
  - a sign can't be both a Domain and an action (same rule as `actions.validate`)
  - hotkeys must parse with pynput (`keyboard.HotKey.parse`) and must not repeat, since a malformed hotkey stops `GlobalHotKeys` at startup *(builder's call, from the review)*
- Unknown keys already in `config.json` are preserved.
- Writes are **atomic** (temp file + `os.replace`), and the previous file is kept as `config.json.bak`.
- The action sign-name field suggests every known sign: built-in signs, Domain names, and taught signs found in `samples/`.

### Renaming signs (Domains and actions)
- **Built-in signs can't be renamed** (`unlimited_void`, `malevolent_shrine`, i.e. the keys of `hand_signs.GESTURES`): their rules are looked up by name, so renaming would break detection. Their **title** (the name shown in the preview) stays editable, which covers the common case.
- **Name rules:** the new name must match `learned_signs.SIGN_NAME`, and must not already be used by a Domain, an action, or an existing `samples/<new>` folder.
- **Order and rollback:** the rename is applied on **Save**, all or nothing:
  1. move the folder `samples/<old>` â†’ `samples/<new>`, if it exists;
  2. write the config (atomically, as for any save).

  If step 1 fails (for example `teach.bat` has the folder open), nothing is saved and the window shows why. If step 2 fails, the folder is moved back.
- **Running app:** the rename appears in the config at once, but the taught sign under its new name is only loaded when the app restarts, because taught signs are loaded at startup. The window says "applies on restart".
- **Unit tests:** folder and config renamed together; rollback when the folder move or the save fails; built-in and duplicate names refused.

### Live reload in the app (`main.py`, new `live_config.py`)
- The main loop checks `config.json`'s modification time about once a second, so the cost is negligible.
- On a change it re-reads the file. If parsing or validation fails (for example a half-written hand edit), it keeps the current settings, prints one warning, and retries on the next change. It never crashes.
- **Applied live:**

  | Setting | How it's applied |
  |---|---|
  | `hold_frames`, `miss_tolerance`, `cooldown_sec` | Updated on every existing `HoldTrigger` (plain attributes) |
  | `quality` | `QualityGovernor` mode updated; switching to `high` resets to full quality, switching to `low` jumps to the lightest level |
  | `show_preview`, `preview_width`, `mirror_preview` | Turning the preview off closes its window; turning it on reopens it |
  | `actions` | Re-validated and swapped in. A clash or bad entry keeps the previous actions and prints why. New actions whose sign has no detector show "record: teach.bat name" in the preview |

- **On restart only:** camera index, width, height, camera fps, output fps (the virtual camera is opened at a fixed rate), and everything under `domains`. Changing these prints "saved; restart the app to apply".
- The pure logic (comparing old and new config, deciding what applies live, applying it to the triggers, governor and preview options) lives in `live_config.py`, so it is unit-testable without a camera.

### Tray icon (`main.py`, new `tray.py`)
- A `pystray` icon is shown while the app runs. The icon image is drawn with Pillow at startup, so there's no asset file.
- **Settings:** opens the settings window process.
- **Quit:** stops the app cleanly, through the same shutdown path as pressing Q.
- The tray runs on its own thread (`run_detached`). Its menu actions hand requests to the main loop the same way hotkeys do now (the lock-protected list).

### Docs
The README gets a "Settings window" section, replacing the instructions to edit `config.json` in Notepad (the settings tables stay as a reference). It also documents `settings.bat` and the tray icon. "Add your own Domain" switches from copying a block to clicking **Add Domain**.

## Left to the builder
- Exact layout, widget choices and spacing.
- Hotkey entry format help (text with an example is fine).
- Whether a second Settings click focuses the existing window or opens another.
- Icon colours.
- Whether to show a small "Saved; applied live" / "restart needed" message in the window after saving.

## Verification
- **Unit tests (`live_config.py`):**
  - each live setting is applied
  - restart-only settings are reported, not applied
  - an invalid or half-written file is ignored safely
  - an action clash keeps the old actions
- **Unit tests (settings model):** atomic save with backup; unknown keys preserved; validation messages; sign rename with recordings and rollback.
- **Headless check:** reuse the fake-camera benchmark script from the performance work. It lives in the session scratchpad and is not committed: it monkeypatches `main.open_camera` with a fake capture, wraps `pyvirtualcam.Camera.send` to count frames, and runs against the real OBS virtual camera, which is installed on this PC. Edit `config.json` mid-run and confirm `hold_frames` and `actions` change without a restart and without an fps drop.
- **Manual check on this PC:** `settings.bat` opens the window, edits round-trip to `config.json`, and **Start app** launches the app (it stops at the camera message here, since this PC has no webcam). The full flow, including the tray, gets checked on the laptop.
