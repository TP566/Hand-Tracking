# Hand-Tracking

Hand tracking for personal and entertainment use.

Perform Gojo's **Unlimited Void** hand sign (index and middle finger crossed) on camera and your background turns into the Domain Expansion while you stay in front of it. The result is sent to the **OBS Virtual Camera**, so it works in Discord, Zoom, Teams or anything else that takes a webcam.

## How it works

1. OpenCV reads your webcam.
2. MediaPipe `HandLandmarker` finds hand landmarks; `hand_signs.py` checks them for the sign.
3. Holding the sign for a moment toggles the Domain. The opening plays once, then the "already open" part loops until you make the sign again or press the hotkey.
4. MediaPipe `ImageSegmenter` cuts you out of the frame and the Domain video is composited behind you.
5. The composited frame is sent to the OBS Virtual Camera via `pyvirtualcam`.

## Setup (Windows)

Requirements: Python 3.12+ and [OBS Studio](https://obsproject.com/) installed (it provides the virtual camera driver; OBS does not need to be running).

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python setup_models.py
```

Put your Domain video in the project folder and set `video_path` in `config.json`. Video files are git-ignored.

## Run

```bash
python main.py
```

Then in Discord: **User Settings → Voice & Video → Camera → OBS Virtual Camera**. The app holds the physical webcam while it runs, so Discord must use the virtual camera.

- Make the sign (hold ~0.4 s) to open the Domain, and again to close it.
- Global hotkey (works while Discord is focused): `Ctrl+Alt+D` by default.
- Press `q` in the preview window to quit.

The preview window shows landmarks, state and FPS; those overlays are never sent to the virtual camera.

## Configuration (`config.json`)

| Key | Meaning |
|-----|---------|
| `camera_index` | Webcam index (0 = first camera) |
| `width`, `height`, `fps` | Capture and virtual camera format |
| `video_path` | Domain video file |
| `loop_start_sec` | Where the looping "Domain open" part begins; everything before it plays once |
| `loop_end_sec` | Where the loop ends (`null` = end of file) |
| `hold_frames` | Consecutive frames the sign must be held to trigger |
| `cooldown_sec` | Time after a trigger during which the sign is ignored |
| `hotkey` | `pynput` hotkey string, e.g. `<ctrl>+<alt>+d` |
| `mirror_preview` | Mirror the local preview (the virtual camera is never mirrored) |
| `show_preview` | Show the local preview window |

## Adding a gesture

Gesture detectors live in `hand_signs.py`. Each takes the 21 landmarks plus handedness and returns `True` when the sign is present. Add a function and register it in `GESTURES`; `main.py` creates a `HoldTrigger` per gesture and dispatches to the action mapped in `ACTIONS`, which is where PyAutoGUI-based actions will go.

## Tests

```bash
pytest
```
