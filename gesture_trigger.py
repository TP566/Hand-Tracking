"""Debounce a per-frame gesture signal into a single trigger event."""

import time
from typing import Callable


class HoldTrigger:
    """Fires once when a gesture has been held for ``hold_frames`` frames.

    Up to ``miss_tolerance`` consecutive missed frames are forgiven during a hold,
    since landmarks drop out briefly when fingers overlap. After firing, the
    gesture must be released (after ``cooldown_sec``) before it can fire again,
    so holding the sign does not toggle repeatedly.
    """

    def __init__(self, hold_frames: int, cooldown_sec: float, miss_tolerance: int = 3,
                 clock: Callable[[], float] = time.monotonic):
        self.hold_frames = max(1, hold_frames)
        self.cooldown_sec = cooldown_sec
        self.miss_tolerance = max(0, miss_tolerance)
        self.clock = clock
        self.count = 0
        self.misses = 0
        self.armed = True
        self.cooldown_until = 0.0

    @property
    def progress(self) -> float:
        """Fraction of the hold completed, for UI feedback."""
        return min(1.0, self.count / self.hold_frames) if self.armed else 0.0

    def update(self, active: bool) -> bool:
        now = self.clock()
        if not active:
            self.misses += 1
            if self.misses > self.miss_tolerance:
                self.count = 0
                if now >= self.cooldown_until:
                    self.armed = True
            return False
        self.misses = 0
        if not self.armed:
            return False
        self.count += 1
        if self.count >= self.hold_frames:
            self.count = 0
            self.armed = False
            self.cooldown_until = now + self.cooldown_sec
            return True
        return False
