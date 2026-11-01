"""Hand-sign triggered Domain Expansion background, sent to the OBS Virtual Camera."""

import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import pyvirtualcam
from pynput import keyboard

import setup_models
import video_cache
from compositor import PersonSegmenter, composite
from domain import DomainManager, DomainPlayer, PrefetchSource
from gesture_trigger import HoldTrigger
from hand_detector import HandDetector, draw_hand, draw_text
from hand_signs import GESTURES
from pipeline import QUALITY_LEVELS, CameraReader, QualityGovernor, Stats, Worker

ROOT = Path(__file__).parent
MODELS = ROOT / "models"
VIDEOS = ROOT / "videos"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi")
SIGN_TITLES = {"unlimited_void": "Unlimited Void", "malevolent_shrine": "Malevolent Shrine"}
HAND_DETECT_RATE = 30  # hand detections per second at most


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
    # MJPG lets most webcams deliver 720p at 60 fps; cameras that refuse it keep their default format.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["height"])
    cap.set(cv2.CAP_PROP_FPS, cfg.get("camera_fps", cfg["fps"]))
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
        players[name] = DomainPlayer(PrefetchSource(str(video)), domain_cfg["loop_start_sec"],
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


def make_hand_stage(detector: HandDetector, triggers: dict[str, HoldTrigger],
                    post: Callable[[str], None]) -> Callable:
    """Hand worker step: detect hands, advance the hold triggers, post fired signs."""
    last_ts = [0]

    def run(frame: np.ndarray):
        # MediaPipe VIDEO mode requires strictly increasing timestamps.
        last_ts[0] = max(last_ts[0] + 1, int(time.monotonic() * 1000))
        hands = detector.detect(frame, last_ts[0])
        for name, detect in GESTURES.items():
            if triggers[name].update(detect(hands)):
                post(name)
        return hands
    return run


def make_segment_stage(segmenter: PersonSegmenter, reset: threading.Event) -> Callable:
    """Segmentation worker step; ``reset`` clears the temporal smoothing (set when a Domain opens)."""
    last_ts = [0]

    def run(frame: np.ndarray):
        if reset.is_set():
            segmenter.reset()
            reset.clear()
        last_ts[0] = max(last_ts[0] + 1, int(time.monotonic() * 1000))
        return segmenter.mask(frame, last_ts[0])
    return run


def even(x: float) -> int:
    return max(2, int(x) // 2 * 2)


def main() -> None:
    show_stats = "--stats" in sys.argv
    cfg = load_config()
    ensure_models()
    cap = open_camera(cfg)
    ok, frame = cap.read()
    height, width = frame.shape[:2]
    domains = build_domains(cfg, width, height)
    fps = cfg["fps"]

    triggers = {name: HoldTrigger(cfg["hold_frames"], cfg["cooldown_sec"], cfg.get("miss_tolerance", 3))
                for name in GESTURES}
    detector = HandDetector(str(MODELS / "hand_landmarker.task"))
    segmenter = PersonSegmenter(str(MODELS / "selfie_segmenter_landscape.tflite"))

    # Signs fire on the hand worker's thread and hotkeys on pynput's; both hand them
    # to the main loop through this list.
    sign_hits: list[str] = []
    lock = threading.Lock()

    def post(name: str) -> None:
        with lock:
            sign_hits.append(name)

    hotkeys = keyboard.GlobalHotKeys({d["hotkey"]: (lambda n=name: post(n))
                                      for name, d in cfg["domains"].items()})
    hotkeys.start()

    camera = CameraReader(cap)
    # Workers are capped: segmenting faster than frames are sent wastes CPU, and a fixed hand
    # detection rate keeps hold_frames meaning the same time on every PC and at any output fps.
    hand_rate = min(fps, HAND_DETECT_RATE)
    hand_worker = Worker("hands", make_hand_stage(detector, triggers, post), camera.frames, max_rate=hand_rate)
    seg_reset = threading.Event()
    seg_worker = Worker("segment", make_segment_stage(segmenter, seg_reset), camera.frames,
                        max_rate=fps, paused=True)
    governor = QualityGovernor(cfg.get("quality", "auto"))
    out_stats, blend_stats = Stats(), Stats()

    def apply_quality(level: int) -> tuple[int, int]:
        hand_worker.max_rate = hand_rate / 2 if level >= 1 else hand_rate
        seg_worker.max_rate = fps / 2 if level >= 2 else fps
        return (even(width * 0.75), even(height * 0.75)) if level >= 3 else (width, height)

    blend_size = apply_quality(governor.level)
    for thread in (camera, hand_worker, seg_worker):
        thread.start()
    print(f"Camera {width}x{height}. Select 'OBS Virtual Camera' in Discord. Press 'q' in the preview to quit.")

    preview_w = min(width, cfg.get("preview_width", 640))
    preview_scale = preview_w / width
    was_active = False
    seen = 0
    next_report = time.monotonic() + 5
    decoded_at_report = 0

    try:
        try:
            cam_ctx = pyvirtualcam.Camera(width, height, fps, backend="obs",
                                          fmt=pyvirtualcam.PixelFormat.BGR)
        except RuntimeError as e:
            raise SystemExit(f"Could not start the OBS Virtual Camera ({e}).\n"
                             "- If OBS is open with 'Start Virtual Camera' on, click 'Stop Virtual Camera'. "
                             "This app feeds the virtual camera itself; only one program can at a time.\n"
                             "- If OBS Studio is not installed, install it from https://obsproject.com/") from None
        with cam_ctx as cam:
            while True:
                version, frame = camera.frames.wait_newer(seen, 1.0)
                for worker in (hand_worker, seg_worker):
                    if worker.error:
                        raise worker.error
                if camera.ended:
                    break
                if version == seen:
                    continue
                seen = version

                with lock:
                    pending, sign_hits[:] = list(sign_hits), []
                for name in pending:
                    domains.on_sign(name)
                active = domains.active is not None
                if active and not was_active:
                    seg_worker.output.set(None)
                    seg_reset.set()
                    seg_worker.resume()
                elif was_active and not active:
                    seg_worker.pause()
                was_active = active

                start = time.monotonic()
                bw, bh = blend_size
                background = domains.current_frame(bw, bh)
                mask = seg_worker.output.get()[1]
                if background is None or mask is None:
                    output = frame
                else:
                    person = frame if bw == width else cv2.resize(frame, (bw, bh), interpolation=cv2.INTER_AREA)
                    output = composite(person, background, mask)
                    if bw != width:
                        output = cv2.resize(output, (width, height), interpolation=cv2.INTER_LINEAR)
                    blend_stats.record(time.monotonic() - start)
                cam.send(output)
                out_stats.record()

                cam_fps = camera.stats.rate
                if governor.update(out_stats.rate, min(fps, cam_fps)):
                    blend_size = apply_quality(governor.level)
                    print(f"Running below {fps} fps: switched to '{QUALITY_LEVELS[governor.level]}' "
                          "(set \"quality\": \"high\" in config.json to keep full quality).")

                quality = QUALITY_LEVELS[governor.level]
                summary = f"FPS {out_stats.rate:.0f} (camera {cam_fps:.0f})  {quality}"
                timings = (f"hands {hand_worker.stats.ms:.0f}ms  cut-out {seg_worker.stats.ms:.0f}ms  "
                           f"blend {blend_stats.ms:.0f}ms")
                now = time.monotonic()
                if show_stats and now >= next_report:
                    decoded = sum(getattr(p.source, "decoded", 0) for p in domains.players.values())
                    print(f"{summary} | {timings} | hands {hand_worker.stats.rate:.0f}/s  "
                          f"cut-out {seg_worker.stats.rate:.0f}/s  video {(decoded - decoded_at_report) / 5:.0f}/s")
                    next_report, decoded_at_report = now + 5, decoded

                if cfg.get("show_preview", True):
                    # Shrink first so the overlays and the window are cheap; the virtual camera keeps full size.
                    preview = cv2.resize(output, (preview_w, round(height * preview_scale)),
                                         interpolation=cv2.INTER_AREA)
                    for hand in hand_worker.output.get()[1] or []:
                        draw_hand(preview, [(x * preview_scale, y * preview_scale) for x, y in hand.image],
                                  (255, 80, 200))
                    if cfg.get("mirror_preview", True):
                        preview = cv2.flip(preview, 1)
                    title = SIGN_TITLES.get(domains.active, domains.active) if domains.active else "none"
                    draw_status(preview, [f"Domain: {title} ({domains.state.value})", summary, timings],
                                [(SIGN_TITLES.get(n, n), triggers[n].progress, n in domains.players)
                                 for n in GESTURES])
                    cv2.imshow("Domain Expansion (preview)", preview)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                cam.sleep_until_next_frame()
    finally:
        hotkeys.stop()
        for thread in (camera, hand_worker, seg_worker):
            thread.stop()
            thread.join(timeout=2.0)
        cap.release()
        detector.close()
        segmenter.close()
        for player in domains.players.values():
            getattr(player.source, "close", lambda: None)()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
