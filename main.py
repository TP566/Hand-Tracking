"""Hand-sign triggered Domain Expansion background, sent to the OBS Virtual Camera."""

import json
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import pyvirtualcam
from mediapipe.tasks.python import BaseOptions, vision
from pynput import keyboard

from compositor import PersonSegmenter, composite
from domain import DomainPlayer, VideoFileSource
from gesture_trigger import HoldTrigger
from hand_signs import GESTURES

ROOT = Path(__file__).parent
MODELS = ROOT / "models"
DETECT_WIDTH = 640
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


class HandDetector:
    def __init__(self, model_path: str):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> list[tuple[list[tuple[float, float]], str]]:
        """Return (landmarks in pixels, handedness) for each detected hand."""
        h, w = frame_bgr.shape[:2]
        # Landmarks are normalised, so detecting on a smaller copy is cheaper and loses little.
        if w > DETECT_WIDTH:
            frame_bgr = cv2.resize(frame_bgr, (DETECT_WIDTH, round(h * DETECT_WIDTH / w)),
                                   interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
        hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            points = [(p.x * w, p.y * h) for p in landmarks]
            hands.append((points, handedness[0].category_name if handedness else ""))
        return hands

    def close(self) -> None:
        self.landmarker.close()


def draw_hand(img: np.ndarray, points: list[tuple[float, float]], color: tuple[int, int, int]) -> None:
    pts = [(int(x), int(y)) for x, y in points]
    for a, b in HAND_CONNECTIONS:
        cv2.line(img, pts[a], pts[b], color, 2)
    for p in pts:
        cv2.circle(img, p, 3, (255, 255, 255), -1)


def draw_status(img: np.ndarray, lines: list[str], progress: float) -> None:
    for i, text in enumerate(lines):
        org = (12, 28 + 26 * i)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    if progress > 0:
        top = 28 + 26 * len(lines)
        cv2.rectangle(img, (12, top), (12 + int(img.shape[1] // 3 * progress), top + 10), (255, 80, 200), -1)


def main() -> None:
    cfg = load_config()
    player = DomainPlayer(VideoFileSource(str(ROOT / cfg["video_path"])),
                          cfg["loop_start_sec"], cfg.get("loop_end_sec"))
    triggers = {name: HoldTrigger(cfg["hold_frames"], cfg["cooldown_sec"]) for name in GESTURES}
    # Gesture name -> action. Future PyAutoGUI actions are registered here.
    actions = {"unlimited_void": player.toggle}

    cap = cv2.VideoCapture(cfg["camera_index"], cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["height"])
    cap.set(cv2.CAP_PROP_FPS, cfg["fps"])
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError(f"Cannot read from camera {cfg['camera_index']}")
    height, width = frame.shape[:2]

    hands = HandDetector(str(MODELS / "hand_landmarker.task"))
    segmenter = PersonSegmenter(str(MODELS / "selfie_segmenter.tflite"))

    hotkey_pressed = threading.Event()
    hotkeys = keyboard.GlobalHotKeys({cfg["hotkey"]: hotkey_pressed.set})
    hotkeys.start()

    last_ts = 0
    fps_avg = 0.0
    prev_time = time.monotonic()
    print(f"Camera {width}x{height}. Select 'OBS Virtual Camera' in Discord. "
          f"Hotkey {cfg['hotkey']} toggles the Domain, 'q' in the preview quits.")

    try:
        with pyvirtualcam.Camera(width, height, cfg["fps"], backend="obs",
                                 fmt=pyvirtualcam.PixelFormat.BGR) as cam:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                # MediaPipe VIDEO mode requires strictly increasing timestamps.
                ts = max(last_ts + 1, int(time.monotonic() * 1000))
                last_ts = ts

                detected = hands.detect(frame, ts)
                for name, detector in GESTURES.items():
                    active = any(detector(points, side) for points, side in detected)
                    if triggers[name].update(active):
                        actions[name]()
                if hotkey_pressed.is_set():
                    hotkey_pressed.clear()
                    player.toggle()

                background = player.current_frame(width, height)
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
                    for points, _ in detected:
                        draw_hand(preview, points, (255, 80, 200))
                    if cfg.get("mirror_preview", True):
                        preview = cv2.flip(preview, 1)
                    draw_status(preview, [f"Domain: {player.state.value}", f"FPS: {fps_avg:.0f}"],
                                triggers["unlimited_void"].progress)
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
