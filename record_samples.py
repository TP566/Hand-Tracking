"""Record real hand sign samples to tune the built-in signs and teach new ones.

Press a key to start recording a label, the same key (or space) to stop:
  1 = Unlimited Void   2 = Malevolent Shrine   0 = not a sign   q = quit
With --sign NAME (teach.bat NAME):
  R = record the new sign NAME   T = retrain now and test it live
While recording, every 3rd frame with a detected hand is saved to samples/<label>/.
"""

import argparse
import json
import time
from pathlib import Path

import cv2

from hand_detector import HandDetector, draw_hand, draw_text
from learned_signs import MIN_SAMPLES, SIGN_NAME, build_gestures
from main import MODELS, ensure_models, load_config, open_camera

ROOT = Path(__file__).parent
SAMPLES = ROOT / "samples"
SAVE_EVERY = 3


def count_samples(labels) -> dict[str, int]:
    return {label: len(list((SAMPLES / label).glob("*.json"))) for label in labels}


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record hand sign samples.")
    parser.add_argument("--sign", help="name of a new sign to teach (letters, digits and _ only)")
    args = parser.parse_args()
    if args.sign and not SIGN_NAME.match(args.sign):
        raise SystemExit(f"'{args.sign}' is not a valid sign name: use letters, digits and _ only "
                         "(for example mute or idle_death_gamble).")
    return args


def main() -> None:
    args = parse_args()
    labels = {ord("1"): "unlimited_void", ord("2"): "malevolent_shrine", ord("0"): "none"}
    if args.sign:
        labels[ord("r")] = args.sign
    cfg = load_config()
    ensure_models()
    cap = open_camera(cfg)
    detector = HandDetector(str(MODELS / "hand_landmarker.task"))
    gestures, _ = build_gestures(SAMPLES)
    recording = None
    frame_no = 0
    last_ts = 0
    counts = count_samples(labels.values())
    print(__doc__)
    if args.sign:
        print(f"Teaching '{args.sign}': press R and hold the sign, moving a little (front, side, tilted, "
              f"near, far). Then press 0 and record poses that are NOT the sign. "
              f"Press T to test. At least {MIN_SAMPLES} frames are needed.")
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
            seen = [name for name, fn in gestures.items() if fn(hands)]
            keys = "1 = Unlimited Void   2 = Malevolent Shrine   0 = not a sign   q = quit"
            if args.sign:
                keys = f"R = record '{args.sign}'   0 = not a sign   T = test   q = quit"
            draw_text(preview, keys, 0)
            draw_text(preview, f"Detected now: {', '.join(seen) or '-'}", 1)
            draw_text(preview, "Saved: " + "  ".join(f"{k} {v}" for k, v in counts.items()), 2)
            if recording:
                draw_text(preview, f"REC {recording}  (press again or space to stop)", 3, (60, 60, 255))
            cv2.imshow("Record hand signs", preview)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("t") and args.sign:
                recording = None
                gestures, messages = build_gestures(SAMPLES)
                print("\n".join(messages) or f"Retrained. Hold '{args.sign}' and watch 'Detected now'.")
            elif key == ord(" ") or (key in labels and labels[key] == recording):
                recording = None
            elif key in labels:
                recording = labels[key]
    finally:
        cap.release()
        detector.close()
        cv2.destroyAllWindows()
    print("Saved samples:", count_samples(labels.values()))


if __name__ == "__main__":
    main()
