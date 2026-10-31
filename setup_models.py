"""Download the MediaPipe model files used by the app into models/."""

import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"
MODELS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "selfie_segmenter.tflite": "https://storage.googleapis.com/mediapipe-models/"
    "image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
}


def main() -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    for name, url in MODELS.items():
        target = MODELS_DIR / name
        if target.exists():
            print(f"{name}: already present")
            continue
        print(f"{name}: downloading...")
        urllib.request.urlretrieve(url, target)
        print(f"{name}: {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
