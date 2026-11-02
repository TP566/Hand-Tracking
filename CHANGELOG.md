# Changelog

Versions are git tags on GitHub (**Code → Tags**).

- **Release** versions (`v2.0.0`, `v2.1.0`, `v3.0.0`): major updates, merged after a full review. Use these.
- **Beta** versions (`v2.1.0-beta.1`, `v2.1.0-beta.2`): small updates merged between releases, to try before the next release.

## v2.0.0 (2026-11-02) - release

- **Settings window** (`settings.bat`): edit every setting without opening `config.json`. Tabs: General, Signs, Domains, Actions.
  - Sign sensitivity, performance and PC actions apply to the running app about a second after saving. Camera, resolution, output fps and Domains apply on restart.
  - Add, remove and rename Domains. A rename moves the taught sign's recordings with it.
  - Saves are atomic and keep `config.json.bak`. A bad hand edit is ignored with a warning instead of crashing the app.
- **Tray icon** while the app runs, with *Settings* and *Quit*. The app refuses to start twice.
- **Start app** from the settings window runs `run.bat`, so startup errors stay readable.
- Domain hotkeys must include a modifier key (for example `<ctrl>+<alt>+d`).
- `config.json` saved with a BOM now loads.
- Upgrading from v1.0.0: run `setup.bat` once to install the new packages (pystray, Pillow). Until then the app runs without the tray icon and says so.

## v1.0.0 - release

The original `.bat` version: `setup.bat`, `run.bat`, `record.bat`, `teach.bat`, with settings edited in `config.json` by hand.

- Unlimited Void (front and side angles) and Malevolent Shrine signs, tuned on recorded samples, with look-alike poses rejected.
- The Domain video plays its opening once, then loops behind you through the OBS Virtual Camera.
- Threaded pipeline with an automatic quality fallback for slower PCs.
- Teach-a-sign mode, and signs that trigger PC actions (Discord mute/deafen preset).
- Idle Death Gamble Domain slot, and add-your-own Domains.
