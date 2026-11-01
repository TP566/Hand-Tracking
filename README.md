# Hand-Tracking: Domain Expansion

Hand tracking for personal and entertainment use.

Make a Domain Expansion hand sign in front of your webcam and your background turns into that Domain, while you stay in front of it:

- **Gojo: Unlimited Void** (one hand, index and middle fingers crossed)
- **Sukuna: Malevolent Shrine** (two hands meeting at the fingertips)

It It works in Discord, Zoom, Google Meet, Teams, OBS, or anything else that uses a webcam.

> **Windows only** for now (it uses the OBS Virtual Camera driver).

---

## User guide

### What you need

| | |
|---|---|
| A **webcam** | Built-in laptop cameras work fine |
| **Python 3.10 or newer** | [python.org/downloads](https://www.python.org/downloads/). During install, tick **"Add python.exe to PATH"** |
| **OBS Studio** | [obsproject.com](https://obsproject.com/). Installing it adds the virtual camera this app sends video to; OBS itself stays closed |
| **Domain videos** | An `.mp4` for each Domain you want. Not included in this repository |

### Step 1: Download the project

Either:
- Click the green **Code** button on GitHub → **Download ZIP**, then unzip it somewhere (for example `Documents\Hand-Tracking`), **or**
- With Git: `git clone https://github.com/TP566/Hand-Tracking.git`

### Step 2: Install OBS Studio

Just install it; that adds the **OBS Virtual Camera** device to your computer. You don't need to open OBS to use this app.

> **Important:** do **not** click **Start Virtual Camera** in OBS. This app sends its video into the OBS Virtual Camera by itself, and only one program can do that at a time. If OBS's virtual camera is on, the app can't start, and if the app is running, OBS shows *"Failed to start virtual camera"*. Both are normal.

### Step 3: Run the setup (once)

Double-click **`setup.bat`** in the project folder.

It installs everything the app needs and downloads the hand tracking models. It can take a few minutes the first time. Wait until it says **Setup complete**.

### Step 4: Add your videos

Put your Domain videos in the **`videos`** folder. The app picks each one by its **file name**:

| Domain | The file name must contain | Example |
|---|---|---|
| Unlimited Void | `gojo`, `void` or `unlimited` | `Gojo Satoru Domain Expansion.mp4` |
| Malevolent Shrine | `sukuna`, `shrine` or `malevolent` | `malevolent-shrine-sukuna.mp4` |
| Idle Death Gamble | `hakari`, `gamble` or `idle` | `hakari-idle-death-gamble.mp4` |

You can use just some of them; the others are simply disabled. Big videos (4K, 60 fps) are shrunk once on the first run so they play smoothly. This takes a minute and is saved for next time.

### Step 5: Start the app

Double-click **`run.bat`**.

A **preview window** opens showing your camera. The preview is only for you; the extras drawn on it (hand outline, status text) are never sent to the call.

### Step 6: Use it in your call

In **Discord**: **User Settings (⚙) → Voice & Video → Camera → OBS Virtual Camera**.
Other apps have the same option in their camera or video settings.

> The app is using your real webcam, so your call app must use **OBS Virtual Camera**, not the webcam itself.

### Step 7: Expand your Domain

**Gojo: Unlimited Void** (one hand)
1. Raise one hand towards the camera.
2. Point your **index finger** up and **cross your middle finger** over it. Fold your ring and pinky fingers down.
3. It works from the front or from the side (hand turned sideways to the camera).

**Sukuna: Malevolent Shrine** (two hands)
1. Bring both hands up in front of your chest, fingers pointing up.
2. Touch the **fingertips** of both hands together at the top, and keep your **wrists apart**, so your hands form a triangle like the letter **A**.
3. Interlock your inner fingers as in the anime if you like; the app mainly looks for the "A" shape. (Flat prayer hands, with the wrists together, don't count.)

Hold the sign for about half a second. Its pink bar in the preview fills up, and the Domain opens behind you. The opening plays once, then the open Domain keeps looping.

**To close the Domain:** lower your hands, then make the **same** sign again, or press its hotkey (these work even while Discord is the active window):

| Domain | Hotkey |
|---|---|
| Unlimited Void | **Ctrl + Alt + D** |
| Malevolent Shrine | **Ctrl + Alt + S** |
| Idle Death Gamble | **Ctrl + Alt + H** |

Only one Domain can be open at a time. While one is open, the other signs are ignored until you close it.

**Hakari: Idle Death Gamble** has no built-in sign: you teach it your own (see *Teach a new sign* below). Until then, its hotkey works. Also set `loop_start_sec` for its video in `config.json` (the second where the Domain is fully open).

**To quit:** click the preview window and press **Q**, or close the black console window.

### Tips for reliable detection

- Keep your hands fully in the frame, about 30–80 cm from the camera.
- Good, even lighting on your hands helps a lot.
- For Unlimited Void, show the crossing clearly: the tip of your middle finger should end up on the other side of your index finger.
- For Malevolent Shrine, make sure **both** hands are outlined in pink in the preview.
- Watch the preview: if a hand isn't outlined in pink, the camera can't see it well enough.

### Help improve detection (optional)

If a sign is hard to trigger, or triggers by accident, you can record your own hands so the detection can be tuned to them:

1. Double-click **`record.bat`**.
2. Make a sign and press its key to start recording, then the same key (or **Space**) to stop:
   - **1** = Unlimited Void, **2** = Malevolent Shrine, **0** = *not a sign*
3. Record each sign for a few seconds **from the front, from the side, and tilted**. Move a little while recording.
4. Also record a few seconds of **0** (*not a sign*): a peace sign, an open hand, prayer hands, waving, your hands resting.
5. Press **Q** to quit. The recordings are saved in the **`samples`** folder.
6. Send the `samples` folder back (commit and push it, or copy it to the main PC).

The top of the recorder window shows which sign it currently detects, so you can also use it to see how well each angle works.

The most useful recordings are **0** (*not a sign*) poses that look *almost* like a sign, such as two open hands touching at the fingertips. They show exactly where a sign's rule needs to be stricter.

### Teach a new sign

Any sign can be taught by showing it to the app. No coding is needed.

1. Double-click **`teach.bat`** and type a name for the sign, for example `mute` (letters, digits and `_` only). Or run `teach.bat mute` from a terminal.
2. Make the sign and press **R** to record, then **R** again to stop. Record it for about 10 seconds, moving a little: front, side, tilted, nearer and farther.
3. Press **0** and record about 10 seconds of poses that are **not** the sign, especially similar-looking ones.
4. Press **T** to test. "Detected now" shows the sign's name while you hold it. If it misses an angle, record more of that angle; if it triggers by accident, record more **0**.
5. Press **Q**. The next time you start `run.bat`, the sign works.

### Control your PC with signs

A sign can also press a shortcut, type text or open something. These are listed under `actions` in `config.json`:

```json
"actions": {
  "mute":   {"keys": "ctrl+shift+f9"},
  "deafen": {"keys": "ctrl+shift+f10"}
}
```

| Action | Example | What it does |
|---|---|---|
| `keys` | `{"keys": "ctrl+shift+f9"}` | Presses a keyboard shortcut |
| `type` | `{"type": "gg"}` | Types text |
| `open` | `{"open": "https://discord.com"}` | Opens a website, app or file |

**Discord mute / deafen with a sign:**
1. In Discord: **User Settings (⚙) → Keybinds → Add a Keybind**. Set **Toggle Mute** to **Ctrl + Shift + F9**, and add another for **Toggle Deafen** set to **Ctrl + Shift + F10**. These work even when Discord isn't the active window.
2. Teach the signs: `teach.bat mute` and `teach.bat deafen`.
3. Start `run.bat`. Holding the mute sign now mutes or unmutes you in Discord.

Actions work while a Domain is open too. A sign name can be used for a Domain or for an action, not both.

### Add your own Domain

1. Put the video in the `videos` folder.
2. In `config.json`, copy one of the blocks under `domains`, give it a new name (for example `chimera_shadow_garden`), and set its `title`, `keywords` (words in the video's file name), `loop_start_sec` and `hotkey`.
3. Teach its sign: `teach.bat chimera_shadow_garden` (the same name as the block).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `setup.bat` says **Python was not found** | Install Python and tick **"Add python.exe to PATH"**. Then open a new window and run `setup.bat` again |
| **Could not open camera** | Close other apps using the webcam (Discord, Zoom, Camera app). If you have more than one camera, set `camera_index` in `config.json` to `1`, `2`... |
| **Could not start the OBS Virtual Camera** | If OBS is open with the virtual camera on, click **Stop Virtual Camera** (or close OBS), then run the app again. If OBS isn't installed, install it |
| OBS says **"Failed to start virtual camera"** | Normal while the app is running: the app is already using the virtual camera. You don't need OBS's button at all |
| **No Domain videos found**, or a sign shows **(no video)** | Put the video in the `videos` folder with a matching file name (see Step 4) |
| Malevolent Shrine **never triggers** | Check that both hands are outlined, the fingertips touch at the top, and the wrists are apart. Then try `record.bat` (see *Help improve detection*) |
| Discord shows a **black screen** or "OBS Virtual Camera" shows nothing | Make sure the app is running (preview window open) *before* selecting the camera in Discord |
| The sign **never triggers** | Check that your hand is outlined in the preview, improve lighting, and cross the fingers more clearly. You can lower `hold_frames` in `config.json` |
| It **triggers by accident** | Raise `hold_frames` in `config.json` (for example to `20`) |
| The video **loops from the wrong place** | Change `loop_start_sec` in `config.json` to the second where your video's Domain is fully open |
| Low FPS / choppy video | See *Performance* below |

---

## Performance

The app runs the camera, hand detection, the person cut-out and the Domain video in parallel, so it should send a steady 30 fps on most PCs. The preview shows the current FPS and how long each part takes (`hands`, `cut-out`, `blend`, in milliseconds).

If your PC can't keep up, the app lowers its own workload automatically, one step at a time, and prints what it changed:

1. Checks for hand signs at half rate (a sign takes a little longer to trigger)
2. Updates the person cut-out at half rate
3. Blends the video at 960x540 instead of 1280x720

If it is still slow:

- **Plug in the charger.** Laptops slow down a lot on battery.
- Set the Windows power mode to **Best performance** (Settings → System → Power & battery).
- Close other apps that use the camera or a lot of CPU (games, browsers with many tabs).
- Set `width` to `960` and `height` to `540` in `config.json`.

To report performance, run the app from a terminal with `.venv\Scripts\python.exe main.py --stats`. It prints a timing line every 5 seconds that you can copy and send.

---

## Settings (`config.json`)

Open `config.json` with Notepad to change these. Restart the app after saving.

| Setting | Default | What it does |
|---|---|---|
| `camera_index` | `0` | Which webcam to use (0 = first camera) |
| `width`, `height` | `1280`, `720` | Camera and output resolution |
| `camera_fps` | `60` | Frame rate requested from the webcam (it uses the closest one it supports) |
| `fps` | `30` | Frames per second sent to the call. Discord shows webcams at 30 fps; set `60` only on a fast PC |
| `quality` | `"auto"` | `"auto"` lowers the workload when the PC can't keep up (see *Performance*). `"high"` never lowers it. `"low"` always uses the lightest settings |
| `hold_frames` | `12` | How long to hold a sign before it triggers (hands are checked 30 times a second, so 12 ≈ 0.4 s) |
| `miss_tolerance` | `3` | How many frames the sign may briefly drop out during the hold without restarting it |
| `cooldown_sec` | `1.5` | Wait time after a trigger before the sign works again |
| `mirror_preview` | `true` | Mirror the preview like a selfie camera. The call always gets the normal view |
| `show_preview` | `true` | Show the preview window |
| `preview_width` | `640` | Width of the preview window. Smaller is cheaper; the call always gets full resolution |

Each Domain has its own block under `domains` (`unlimited_void`, `malevolent_shrine`, `idle_death_gamble`). The block's name is also its sign's name:

| Setting | Default (Void / Shrine) | What it does |
|---|---|---|
| `title` | from the name | Name shown in the preview (optional) |
| `video` | `""` | Path to the video. Leave empty to find it in `videos/` by `keywords` |
| `keywords` | see Step 4 | Words to look for in video file names |
| `loop_start_sec` | `9.5` / `3.8` | Where the looping part starts. Everything before it plays once as the opening |
| `loop_end_sec` | `null` | Where the loop ends (`null` = end of the video) |
| `hotkey` | `<ctrl>+<alt>+d` / `<ctrl>+<alt>+s` | Keyboard shortcut to open or close this Domain |

`actions` maps a sign name to a PC action; see *Control your PC with signs*.

---

## For developers

### How it works

Each stage runs on its own thread (`pipeline.py`): the main loop never waits on a model, it combines the newest camera frame, hands, mask and video frame. A `QualityGovernor` steps the workload down when output fps stays low.

1. OpenCV reads the webcam (`CameraReader`).
2. MediaPipe `HandLandmarker` (`hand_detector.py`) finds hand landmarks in both image pixels and 3D world coordinates. `hand_signs.py` checks the built-in signs with geometric rules (the 3D landmarks let Unlimited Void be read even when the hand is edge-on); `learned_signs.py` recognises taught signs by comparing each frame with the recordings in `samples/` (k-nearest neighbours on hand-local landmarks).
3. `gesture_trigger.py` requires the sign to be held (forgiving brief dropouts), so a single noisy frame can't trigger it.
4. `domain.py` plays the opening once, then loops the open Domain; `DomainManager` keeps one Domain open at a time. `PrefetchSource` decodes the video on a background thread, each frame once, and `video_cache.py` downscales large videos once.
5. MediaPipe `ImageSegmenter` (landscape selfie model) cuts you out; `compositor.py` puts the video behind you.
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

The easy way is `teach.bat <name>`: `learned_signs.build_gestures` adds a detector for every label folder in `samples/` with enough recordings. For a hand-written rule, add a function to `hand_signs.py` that takes the list of `Hand`s in the frame (image landmarks, world landmarks, handedness), returns `True` when the sign is present, and register it in `GESTURES`; rules take precedence over recordings with the same name. Each gesture gets its own `HoldTrigger` in `main.py`; when it fires, the main loop sends it to `DomainManager.on_sign` and, if it has an entry in `actions`, runs it through `actions.py`.

### Tests

```bash
pytest
```

`tests/test_samples.py` replays the recordings in `samples/` (made with `record.bat`) through the detectors and the hold trigger. It checks that each sign is detected often enough to fire in its own recordings and never fires in the others, so tuning the thresholds in `hand_signs.py` can be verified against real hands.
