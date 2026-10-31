"""Record real hand sign samples to tune and test the sign detectors.

Press a number key to start recording a label, the same key (or space) to stop:
  1 = Unlimited Void   2 = Malevolent Shrine   0 = not a sign   q = quit
While recording, every 3rd frame with a detected hand is saved to samples/<label>/.
"""

import json
import time
from pathlib import Path

import cv2

from hand_detector import HandDetector, draw_hand, draw_text
from hand_signs import GESTURES
from main import MODELS, ensure_models, load_config, open_camera

ROOT = Path(__file__).parent
SAMPLES = ROOT / "samples"
LABELS = {ord("1"): "unlimited_void", ord("2"): "malevolent_shrine", ord("0"): "none"}
SAVE_EVERY = 3


def count_samples() -> dict[str, int]:
    return {label: len(list((SAMPLES / label).glob("*.json"))) for label in LABELS.values()}


def save_sample(label: str, hands, width: int, height: int) -> None:
    folder = SAMPLES / label
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "label": label,
        "width": width,
        "height": height,
        "hands": [{"image": [list(p) for p in h.image],
                   "world": [list(p) for p in h.world] if h.world else None,
                   "handedness": h.handedness} for h in hands],
    }
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}.json"
    (folder / name).write_text(json.dumps(data), encoding="utf-8")


def main() -> None:
    cfg = load_config()
    ensure_models()
    cap = open_camera(cfg)
    detector = HandDetector(str(MODELS / "hand_landmarker.task"))
    recording = None
    frame_no = 0
    last_ts = 0
    counts = count_samples()
    print(__doc__)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            ts = max(last_ts + 1, int(time.monotonic() * 1000))
            last_ts = ts
            hands = detector.detect(frame, ts)
            frame_no += 1
            if recording and hands and frame_no % SAVE_EVERY == 0:
                save_sample(recording, hands, width, height)
                counts[recording] += 1

            preview = frame.copy()
            for hand in hands:
                draw_hand(preview, hand.image, (255, 80, 200))
            preview = cv2.flip(preview, 1)
            seen = [name for name, fn in GESTURES.items() if fn(hands)]
            draw_text(preview, "1 = Unlimited Void   2 = Malevolent Shrine   0 = not a sign   q = quit", 0)
            draw_text(preview, f"Detected now: {', '.join(seen) or '-'}", 1)
            draw_text(preview, "Saved: " + "  ".join(f"{k} {v}" for k, v in counts.items()), 2)
            if recording:
                draw_text(preview, f"REC {recording}  (press again or space to stop)", 3, (60, 60, 255))
            cv2.imshow("Record hand signs", preview)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord(" ") or (key in LABELS and LABELS[key] == recording):
                recording = None
            elif key in LABELS:
                recording = LABELS[key]
    finally:
        cap.release()
        detector.close()
        cv2.destroyAllWindows()
    print("Saved samples:", count_samples())


if __name__ == "__main__":
    main()
