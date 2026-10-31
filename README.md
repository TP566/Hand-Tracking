# Hand-Tracking: Domain Expansion

Hand tracking for personal and entertainment use.

Make Gojo's **Unlimited Void** hand sign in front of your webcam and your background turns into the Domain Expansion, while you stay in front of it. It works in Discord, Zoom, Google Meet, Teams, OBS, or anything else that uses a webcam.

> **Windows only** for now (it uses the OBS Virtual Camera driver).

---

## User guide

### What you need

| | |
|---|---|
| A **webcam** | Built-in laptop cameras work fine |
| **Python 3.10 or newer** | [python.org/downloads](https://www.python.org/downloads/). During install, tick **"Add python.exe to PATH"** |
| **OBS Studio** | [obsproject.com](https://obsproject.com/). Installs the virtual camera this app sends video to |
| A **Domain video** | Any `.mp4` of the Domain Expansion. Not included in this repository |

### Step 1: Download the project

Either:
- Click the green **Code** button on GitHub → **Download ZIP**, then unzip it somewhere (for example `Documents\Hand-Tracking`), **or**
- With Git: `git clone https://github.com/TP566/Hand-Tracking.git`

### Step 2: Turn on the OBS Virtual Camera (once)

1. Open **OBS Studio**.
2. Click **Start Virtual Camera** (bottom right), then **Stop Virtual Camera**.
3. Close OBS.

You only do this once per computer. OBS does **not** need to be open when you use the app.

### Step 3: Run the setup (once)

Double-click **`setup.bat`** in the project folder.

It installs everything the app needs and downloads the hand tracking models. It can take a few minutes the first time. Wait until it says **Setup complete**.

### Step 4: Add your video

Put your Domain video file in the **`videos`** folder. The app uses the first video it finds there.

### Step 5: Start the app

Double-click **`run.bat`**.

A **preview window** opens showing your camera. The preview is only for you; the extras drawn on it (hand outline, status text) are never sent to the call.

### Step 6: Use it in your call

In **Discord**: **User Settings (⚙) → Voice & Video → Camera → OBS Virtual Camera**.
Other apps have the same option in their camera or video settings.

> The app is using your real webcam, so your call app must use **OBS Virtual Camera**, not the webcam itself.

### Step 7: Expand your Domain

1. Raise one hand towards the camera.
2. Extend your **index and middle fingers** and **cross them** (middle finger over the index), with your ring and pinky fingers folded down.
3. Hold it for about half a second. The pink bar in the preview fills up, and the Domain opens behind you.
4. The opening plays once, then the open Domain keeps looping.

**To close the Domain:** lower your hand, then make the sign again, or press **Ctrl + Alt + D** (works even while Discord is the active window).

**To quit:** click the preview window and press **Q**, or close the black console window.

### Tips for reliable detection

- Keep your hand fully in the frame, about 30–80 cm from the camera.
- Good, even lighting on your hand helps a lot.
- Show the crossing clearly: the tip of your middle finger should end up on the other side of your index finger.
- Watch the preview: if your hand isn't outlined in pink, the camera can't see it well enough.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `setup.bat` says **Python was not found** | Install Python and tick **"Add python.exe to PATH"**. Then open a new window and run `setup.bat` again |
| **Could not open camera** | Close other apps using the webcam (Discord, Zoom, Camera app). If you have more than one camera, set `camera_index` in `config.json` to `1`, `2`... |
| **OBS Virtual Camera is not available** | Do Step 2 again. If OBS isn't installed, install it first |
| **No Domain video found** | Put an `.mp4` in the `videos` folder |
| Discord shows a **black screen** or "OBS Virtual Camera" shows nothing | Make sure the app is running (preview window open) *before* selecting the camera in Discord |
| The sign **never triggers** | Check that your hand is outlined in the preview, improve lighting, and cross the fingers more clearly. You can lower `hold_frames` in `config.json` |
| It **triggers by accident** | Raise `hold_frames` in `config.json` (for example to `20`) |
| The video **loops from the wrong place** | Change `loop_start_sec` in `config.json` to the second where your video's Domain is fully open |
| Low FPS / choppy video | Set `width` to `960` and `height` to `540` in `config.json` |

---

## Settings (`config.json`)

Open `config.json` with Notepad to change these. Restart the app after saving.

| Setting | Default | What it does |
|---|---|---|
| `camera_index` | `0` | Which webcam to use (0 = first camera) |
| `width`, `height` | `1280`, `720` | Camera resolution |
| `fps` | `30` | Frames per second |
| `video_path` | `""` | Path to the video. Leave empty to use the first video in `videos/` |
| `loop_start_sec` | `9.5` | Where the looping part starts. Everything before it plays once as the opening |
| `loop_end_sec` | `null` | Where the loop ends (`null` = end of the video) |
| `hold_frames` | `12` | How long to hold the sign before it triggers (12 frames ≈ 0.4 s) |
| `cooldown_sec` | `1.5` | Wait time after a trigger before the sign works again |
| `hotkey` | `<ctrl>+<alt>+d` | Keyboard shortcut to open or close the Domain |
| `mirror_preview` | `true` | Mirror the preview like a selfie camera. The call always gets the normal view |
| `show_preview` | `true` | Show the preview window |

---

## For developers

### How it works

1. OpenCV reads the webcam.
2. MediaPipe `HandLandmarker` finds hand landmarks; `hand_signs.py` checks them for the sign.
3. `gesture_trigger.py` requires the sign to be held, so a single noisy frame can't trigger it.
4. `domain.py` plays the opening once, then loops the open Domain.
5. MediaPipe `ImageSegmenter` cuts you out; `compositor.py` puts the video behind you.
6. `pyvirtualcam` sends the result to the OBS Virtual Camera.

### Manual setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python setup_models.py
python main.py
```

### Adding a gesture

Gesture detectors live in `hand_signs.py`. Each takes the 21 landmarks plus handedness and returns `True` when the sign is present. Add a function, register it in `GESTURES`, and map it to a function in `actions` in `main.py`. That is where PyAutoGUI-based actions will go.

### Tests

```bash
pytest
```
