"""Person segmentation and background replacement."""

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

# The selfie model runs at 144x256 internally, so segmenting a small frame loses nothing
# and keeps per-pixel mask work (smoothing, feathering) cheap.
MASK_WIDTH = 320


class PersonSegmenter:
    def __init__(self, model_path: str, smoothing: float = 0.5):
        options = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        )
        self.segmenter = vision.ImageSegmenter.create_from_options(options)
        self.smoothing = smoothing
        self._prev: np.ndarray | None = None

    def mask(self, frame_bgr: np.ndarray, timestamp_ms: int) -> np.ndarray:
        """Low-resolution person probability (float32, 0..1), smoothed over time."""
        h, w = frame_bgr.shape[:2]
        small = cv2.resize(frame_bgr, (MASK_WIDTH, round(h * MASK_WIDTH / w)), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        result = self.segmenter.segment_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
        mask = result.confidence_masks[0].numpy_view()[..., 0].copy()
        if self._prev is not None and self._prev.shape == mask.shape:
            mask = self.smoothing * self._prev + (1 - self.smoothing) * mask
        self._prev = mask
        return mask

    def reset(self) -> None:
        self._prev = None

    def close(self) -> None:
        self.segmenter.close()


def composite(person: np.ndarray, background: np.ndarray, mask: np.ndarray,
              feather_px: float = 1.5) -> np.ndarray:
    """Alpha-blend the person over the background.

    ``mask`` may be lower resolution than ``person``; it is feathered at its own
    resolution (``feather_px`` in mask pixels) and then upscaled.
    """
    if feather_px > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), feather_px)
    h, w = person.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(mask, 0.0, 1.0, dtype=np.float32)
    # cv2.blendLinear does the per-pixel blend natively; numpy float math is ~10x slower at 720p.
    return cv2.blendLinear(person, background, alpha, 1.0 - alpha)
