"""Hand-sign triggered Domain Expansion background, sent to the OBS Virtual Camera."""

import json
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pyvirtualcam
from pynput import keyboard

import setup_models
import video_cache
from compositor import PersonSegmenter, composite
from domain import DomainManager, DomainPlayer, VideoFileSource
from gesture_trigger import HoldTrigger
from hand_detector import HandDetector, draw_hand, draw_text
from hand_signs import GESTURES

ROOT = Path(__file__).parent
MODELS = ROOT / "models"
VIDEOS = ROOT / "videos"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi")
SIGN_TITLES = {"unlimited_void": "Unlimited Void", "malevolent_shrine": "Malevolent Shrine"}


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def find_video(name: str, domain_cfg: dict) -> Optional[Path]:
    """The configured video, or the first file in videos/ (or the project folder) named with a keyword."""
    if domain_cfg.get("video"):
        path = ROOT / domain_cfg["video"]
        if path.exists():
            return path
        print(f"[{name}] Video not found: {path}. Check 'video' in config.json.")
        return None
    keywords = [k.lower() for k in domain_cfg.get("keywords", [])]
    for folder in (VIDEOS, ROOT):
        for path in sorted(folder.iterdir()) if folder.exists() else []:
            if path.suffix.lower() in VIDEO_EXTENSIONS and any(k in path.name.lower() for k in keywords):
                return path
    print(f"[{name}] No video found: put a video whose file name contains one of "
          f"{keywords} in the 'videos' folder. This sign is disabled for now.")
    return None


def ensure_models() -> None:
    if not all((MODELS / name).exists() for name in setup_models.MODELS):
        print("Downloading MediaPipe models (first run only)...")
        setup_models.main()


def open_camera(cfg: dict) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(cfg["camera_index"], cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["height"])
    cap.set(cv2.CAP_PROP_FPS, cfg["fps"])
    if not cap.isOpened() or not cap.read()[0]:
        raise SystemExit(f"Could not open camera {cfg['camera_index']}.\n"
                         "Close any app using the webcam (Discord, Zoom, Camera app), "
                         "or try another 'camera_index' in config.json (0, 1, 2...).")
    return cap


def build_domains(cfg: dict, width: int, height: int) -> DomainManager:
    players = {}
    for name, domain_cfg in cfg["domains"].items():
        video = find_video(name, domain_cfg)
        if video is None:
            continue
        video = video_cache.prepare(video, width, height, VIDEOS / ".cache")
        players[name] = DomainPlayer(VideoFileSource(str(video)), domain_cfg["loop_start_sec"],
                                     domain_cfg.get("loop_end_sec"))
        print(f"[{name}] {video.name}  (hotkey {domain_cfg['hotkey']})")
    if not players:
        raise SystemExit("No Domain videos found.\nPut your videos in the 'videos' folder "
                         "(file names containing 'gojo' or 'sukuna', for example) and run again.")
    return DomainManager(players)


def draw_status(img: np.ndarray, lines: list[str], bars: list[tuple[str, float, bool]]) -> None:
    row = 0
    for text in lines:
        draw_text(img, text, row)
        row += 1
    for label, progress, enabled in bars:
        y = draw_text(img, label if enabled else f"{label} (no video)", row,
                      (255, 255, 255) if enabled else (150, 150, 150))
        if progress > 0:
            cv2.rectangle(img, (240, y - 14), (240 + int(200 * progress), y - 2), (255, 80, 200), -1)
        row += 1


def main() -> None:
    cfg = load_config()
    ensure_models()
    cap = open_camera(cfg)
    ok, frame = cap.read()
    height, width = frame.shape[:2]
    domains = build_domains(cfg, width, height)

    triggers = {name: HoldTrigger(cfg["hold_frames"], cfg["cooldown_sec"], cfg.get("miss_tolerance", 3))
                for name in GESTURES}
    hands = HandDetector(str(MODELS / "hand_landmarker.task"))
    segmenter = PersonSegmenter(str(MODELS / "selfie_segmenter.tflite"))

    # Hotkeys fire on pynput's thread; hand them to the main loop through a queue-like list.
    hotkey_hits: list[str] = []
    lock = threading.Lock()

    def on_hotkey(name: str):
        def fire():
            with lock:
                hotkey_hits.append(name)
        return fire

    hotkeys = keyboard.GlobalHotKeys({d["hotkey"]: on_hotkey(name) for name, d in cfg["domains"].items()})
    hotkeys.start()

    last_ts = 0
    fps_avg = 0.0
    prev_time = time.monotonic()
    print(f"Camera {width}x{height}. Select 'OBS Virtual Camera' in Discord. Press 'q' in the preview to quit.")

    try:
        try:
            cam_ctx = pyvirtualcam.Camera(width, height, cfg["fps"], backend="obs",
                                          fmt=pyvirtualcam.PixelFormat.BGR)
        except RuntimeError as e:
            raise SystemExit(f"Could not start the OBS Virtual Camera ({e}).\n"
                             "- If OBS is open with 'Start Virtual Camera' on, click 'Stop Virtual Camera'. "
                             "This app feeds the virtual camera itself; only one program can at a time.\n"
                             "- If OBS Studio is not installed, install it from https://obsproject.com/") from None
        with cam_ctx as cam:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                # MediaPipe VIDEO mode requires strictly increasing timestamps.
                ts = max(last_ts + 1, int(time.monotonic() * 1000))
                last_ts = ts

                detected = hands.detect(frame, ts)
                for name, detector in GESTURES.items():
                    if triggers[name].update(detector(detected)):
                        domains.on_sign(name)
                with lock:
                    pending, hotkey_hits[:] = list(hotkey_hits), []
                for name in pending:
                    domains.on_sign(name)

                background = domains.current_frame(width, height)
                if background is None:
                    output = frame
                    segmenter.reset()
                else:
                    output = composite(frame, background, segmenter.mask(frame, ts))
                cam.send(output)

                if cfg.get("show_preview", True):
                    now = time.monotonic()
                    fps_avg = 0.9 * fps_avg + 0.1 / max(now - prev_time, 1e-6)
                    prev_time = now
                    preview = output.copy()
                    for hand in detected:
                        draw_hand(preview, hand.image, (255, 80, 200))
                    if cfg.get("mirror_preview", True):
                        preview = cv2.flip(preview, 1)
                    active = SIGN_TITLES.get(domains.active, domains.active) if domains.active else "none"
                    draw_status(preview,
                                [f"Domain: {active} ({domains.state.value})", f"FPS: {fps_avg:.0f}"],
                                [(SIGN_TITLES.get(n, n), triggers[n].progress, n in domains.players)
                                 for n in GESTURES])
                    cv2.imshow("Domain Expansion (preview)", preview)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
    finally:
        hotkeys.stop()
        cap.release()
        hands.close()
        segmenter.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
