"""Domain Expansion video playback: play the opening once, then loop the open Domain."""

import time
from enum import Enum
from typing import Callable, Optional, Protocol

import cv2
import numpy as np


class DomainState(Enum):
    IDLE = "IDLE"
    OPENING = "OPENING"
    LOOPING = "LOOPING"


class FrameSource(Protocol):
    fps: float
    frame_count: int

    def read(self, index: int) -> Optional[np.ndarray]: ...


class VideoFileSource:
    """Random-access frame reader over a video file, cheap for forward playback."""

    def __init__(self, path: str):
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.next_index = 0

    def read(self, index: int) -> Optional[np.ndarray]:
        if index < self.next_index or index > self.next_index + 30:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            self.next_index = index
        while self.next_index < index:
            self.cap.grab()
            self.next_index += 1
        ok, frame = self.cap.read()
        self.next_index += 1
        return frame if ok else None


def timeline_frame(elapsed: float, fps: float, loop_start: int, loop_end: int) -> tuple[DomainState, int]:
    """Map seconds since activation to (state, frame index)."""
    index = int(elapsed * fps)
    if index < loop_start:
        return DomainState.OPENING, index
    loop_len = max(1, loop_end - loop_start)
    return DomainState.LOOPING, loop_start + (index - loop_start) % loop_len


def fit_cover(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize to fill width x height, centre-cropping the overflow."""
    h, w = frame.shape[:2]
    scale = max(width / w, height / h)
    resized = cv2.resize(frame, (max(width, round(w * scale)), max(height, round(h * scale))),
                         interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    rh, rw = resized.shape[:2]
    y, x = (rh - height) // 2, (rw - width) // 2
    return resized[y:y + height, x:x + width]


class DomainPlayer:
    def __init__(self, source: FrameSource, loop_start_sec: float, loop_end_sec: Optional[float],
                 clock: Callable[[], float] = time.monotonic):
        self.source = source
        self.clock = clock
        last = max(1, source.frame_count)
        self.loop_end = min(last, round(loop_end_sec * source.fps)) if loop_end_sec else last
        self.loop_start = min(max(0, round(loop_start_sec * source.fps)), self.loop_end - 1)
        self.state = DomainState.IDLE
        self.started_at = 0.0
        self._cache_key: Optional[tuple] = None
        self._cache_frame: Optional[np.ndarray] = None

    @property
    def active(self) -> bool:
        return self.state is not DomainState.IDLE

    def toggle(self) -> None:
        if self.active:
            self.state = DomainState.IDLE
        else:
            self.state = DomainState.OPENING
            self.started_at = self.clock()

    def current_frame(self, width: int, height: int) -> Optional[np.ndarray]:
        """The Domain frame for now, sized to width x height, or None when idle."""
        if not self.active:
            return None
        self.state, index = timeline_frame(self.clock() - self.started_at, self.source.fps,
                                           self.loop_start, self.loop_end)
        key = (index, width, height)
        if key != self._cache_key:
            frame = self.source.read(index)
            if frame is None:
                return self._cache_frame
            self._cache_key, self._cache_frame = key, fit_cover(frame, width, height)
        return self._cache_frame


class DomainManager:
    """Owns one player per Domain; only one Domain can be open at a time."""

    def __init__(self, players: dict[str, DomainPlayer]):
        self.players = players
        self.active: Optional[str] = None

    @property
    def state(self) -> DomainState:
        return self.players[self.active].state if self.active else DomainState.IDLE

    def on_sign(self, name: str) -> None:
        """Open ``name`` if nothing is open, close it if it is the open one, else ignore."""
        if name not in self.players:
            return
        if self.active is None:
            self.players[name].toggle()
            self.active = name
        elif self.active == name:
            self.players[name].toggle()
            self.active = None

    def current_frame(self, width: int, height: int) -> Optional[np.ndarray]:
        return self.players[self.active].current_frame(width, height) if self.active else None
