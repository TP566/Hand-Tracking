"""MediaPipe hand landmark detection and drawing, shared by the app and the recorder."""

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from hand_signs import Hand

DETECT_WIDTH = 640
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


class HandDetector:
    def __init__(self, model_path: str):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> list[Hand]:
        """Detect up to two hands; image landmarks are in pixels of ``frame_bgr``."""
        h, w = frame_bgr.shape[:2]
        # Landmarks are normalised, so detecting on a smaller copy is cheaper and loses little.
        if w > DETECT_WIDTH:
            frame_bgr = cv2.resize(frame_bgr, (DETECT_WIDTH, round(h * DETECT_WIDTH / w)),
                                   interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
        hands = []
        for i, landmarks in enumerate(result.hand_landmarks):
            world = result.hand_world_landmarks[i] if i < len(result.hand_world_landmarks) else None
            handedness = result.handedness[i][0].category_name if i < len(result.handedness) else ""
            hands.append(Hand(
                image=[(p.x * w, p.y * h) for p in landmarks],
                world=[(p.x, p.y, p.z) for p in world] if world else None,
                handedness=handedness,
            ))
        return hands

    def close(self) -> None:
        self.landmarker.close()


def draw_hand(img: np.ndarray, points, color: tuple[int, int, int]) -> None:
    pts = [(int(x), int(y)) for x, y in points]
    for a, b in HAND_CONNECTIONS:
        cv2.line(img, pts[a], pts[b], color, 2)
    for p in pts:
        cv2.circle(img, p, 3, (255, 255, 255), -1)


def draw_text(img: np.ndarray, text: str, row: int, color=(255, 255, 255)) -> int:
    """Outlined text on line ``row``; returns the y of its baseline."""
    y = 28 + 26 * row
    cv2.putText(img, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
    cv2.putText(img, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return y
