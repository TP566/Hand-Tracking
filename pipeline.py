"""Threading pieces that let each stage run at its own pace.

OpenCV and MediaPipe release the GIL while they work, so the camera reader,
hand detector, segmenter and video decoder really run in parallel. The main
loop never waits on a model: it always combines the newest result of each.
"""

import threading
import time
from collections import deque
from typing import Any, Callable, Optional

import cv2


class Latest:
    """Holds the newest value of something, with a version that counts updates."""

    def __init__(self, value: Any = None):
        self._cond = threading.Condition()
        self._value = value
        self.version = 0

    def set(self, value: Any) -> None:
        with self._cond:
            self._value = value
            self.version += 1
            self._cond.notify_all()

    def get(self) -> tuple[int, Any]:
        with self._cond:
            return self.version, self._value

    def wait_newer(self, version: int, timeout: float) -> tuple[int, Any]:
        """Wait until the version is above ``version`` (or the timeout), then return (version, value)."""
        with self._cond:
            self._cond.wait_for(lambda: self.version > version, timeout)
            return self.version, self._value


class Stats:
    """Rolling call rate (per second) and average duration (ms) of a stage."""

    def __init__(self, window_sec: float = 2.0, clock: Callable[[], float] = time.monotonic):
        self.window = window_sec
        self.clock = clock
        self._times: deque[float] = deque()
        self._ms = 0.0
        self._lock = threading.Lock()

    def record(self, duration_sec: float = 0.0) -> None:
        now = self.clock()
        with self._lock:
            self._times.append(now)
            self._ms = duration_sec * 1000 if self._ms == 0 else 0.9 * self._ms + 100 * duration_sec

    @property
    def rate(self) -> float:
        now = self.clock()
        with self._lock:
            while self._times and self._times[0] < now - self.window:
                self._times.popleft()
            return len(self._times) / self.window

    @property
    def ms(self) -> float:
        return self._ms


class CameraReader(threading.Thread):
    """Reads the camera continuously so the newest frame is always ready."""

    def __init__(self, cap: cv2.VideoCapture):
        super().__init__(name="camera", daemon=True)
        self.cap = cap
        self.frames = Latest()
        self.stats = Stats()
        self.ended = False
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            ok, frame = self.cap.read()
            if not ok:
                self.ended = True
                return
            self.stats.record()
            self.frames.set(frame)

    def stop(self) -> None:
        self._stop_event.set()


class Worker(threading.Thread):
    """Runs ``fn`` on the newest item from ``source`` and publishes the result to ``output``.

    Items that arrive while ``fn`` is busy are skipped, never queued, so a slow
    stage lags by at most one item instead of falling further behind.
    ``max_rate`` caps how often it runs (calls per second, 0 = no cap).
    """

    def __init__(self, name: str, fn: Callable[[Any], Any], source: Latest, max_rate: float = 0.0,
                 paused: bool = False):
        super().__init__(name=name, daemon=True)
        self.fn = fn
        self.source = source
        self.max_rate = max_rate
        self.output = Latest()
        self.stats = Stats()
        self.error: Optional[BaseException] = None
        self._running = threading.Event()
        self._stop_event = threading.Event()
        if not paused:
            self._running.set()

    def run(self) -> None:
        seen = self.source.version
        last_start = 0.0
        try:
            while not self._stop_event.is_set():
                if not self._running.wait(0.1):
                    continue
                if self.max_rate > 0:
                    wait = last_start + 1.0 / self.max_rate - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                version, item = self.source.wait_newer(seen, 0.1)
                if version == seen or not self._running.is_set():
                    continue
                seen = version
                last_start = time.monotonic()
                result = self.fn(item)
                self.stats.record(time.monotonic() - last_start)
                self.output.set(result)
        except BaseException as e:  # surfaced to the main loop through ``error``
            self.error = e

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._running.set()


QUALITY_LEVELS = [
    "full quality",
    "hand detection at half rate",
    "person cut-out at half rate",
    "compositing at 960x540",
]


class QualityGovernor:
    """Steps quality down, one level at a time, when output fps stays below target.

    Only steps down, never back up, so quality doesn't flip-flop during a call.
    """

    def __init__(self, mode: str = "auto", threshold: float = 0.85, window_sec: float = 5.0,
                 warmup_sec: float = 3.0, clock: Callable[[], float] = time.monotonic):
        self.mode = mode
        self.level = len(QUALITY_LEVELS) - 1 if mode == "low" else 0
        self.threshold = threshold
        self.window = window_sec
        self.clock = clock
        self._ignore_until = clock() + warmup_sec
        self._slow_since: Optional[float] = None

    def update(self, fps: float, target_fps: float) -> bool:
        """Feed the current output fps and achievable target; True when the level just dropped."""
        if self.mode != "auto" or self.level == len(QUALITY_LEVELS) - 1:
            return False
        now = self.clock()
        if now < self._ignore_until or fps >= self.threshold * target_fps:
            self._slow_since = None
            return False
        if self._slow_since is None:
            self._slow_since = now
            return False
        if now - self._slow_since < self.window:
            return False
        self.level += 1
        self._slow_since = None
        self._ignore_until = now + 2.0  # let the change settle before judging again
        return True
