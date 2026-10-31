"""Rule-based hand sign detectors over MediaPipe's 21 hand landmarks.

Each detector takes ``landmarks`` (21 ``(x, y)`` points in pixel coordinates,
y pointing down) and ``handedness`` ("Left"/"Right", may be unused) and
returns ``True`` when the sign is present.
"""

import math
from typing import Callable, Sequence

Point = Sequence[float]

WRIST = 0
FINGERS = {
    # name: (MCP, PIP, DIP, TIP)
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

# Tip must be this much farther from the wrist than the PIP joint to count as extended.
EXTENDED_RATIO = 1.1
# Crossed tips must be closer than this fraction of the palm length.
CROSS_MAX_TIP_GAP = 0.45
# Tips must be swapped by at least this fraction of the palm length (filters jitter
# when the two fingers are merely held together).
CROSS_MIN_SWAP = 0.03


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def palm_length(lm: Sequence[Point]) -> float:
    """Wrist to middle-finger MCP distance, used as the hand's size scale."""
    return _dist(lm[WRIST], lm[FINGERS["middle"][0]]) or 1e-6


def finger_extended(lm: Sequence[Point], finger: str) -> bool:
    _, pip, _, tip = FINGERS[finger]
    return _dist(lm[WRIST], lm[tip]) > _dist(lm[WRIST], lm[pip]) * EXTENDED_RATIO


def finger_curled(lm: Sequence[Point], finger: str) -> bool:
    _, pip, _, tip = FINGERS[finger]
    return _dist(lm[WRIST], lm[tip]) < _dist(lm[WRIST], lm[pip])


def side_offset(lm: Sequence[Point], idx: int) -> float:
    """Signed distance of a landmark across the palm, in a hand-local frame.

    The frame's "up" axis runs from the wrist to the middle MCP, so the value
    is independent of how the hand is rotated in the image.
    """
    wx, wy = lm[WRIST][0], lm[WRIST][1]
    mx, my = lm[FINGERS["middle"][0]][0], lm[FINGERS["middle"][0]][1]
    ux, uy = mx - wx, my - wy
    norm = math.hypot(ux, uy) or 1e-6
    sx, sy = -uy / norm, ux / norm
    px, py = lm[idx][0] - wx, lm[idx][1] - wy
    return px * sx + py * sy


def fingers_crossed(lm: Sequence[Point], a: str = "index", b: str = "middle") -> bool:
    """True when finger tips ``a`` and ``b`` sit on the opposite sides from their knuckles.

    Comparing the order at the knuckles with the order at the tips works for
    either hand and whether the palm or the back of the hand faces the camera.
    """
    scale = palm_length(lm)
    knuckle_order = side_offset(lm, FINGERS[a][0]) - side_offset(lm, FINGERS[b][0])
    tip_order = side_offset(lm, FINGERS[a][3]) - side_offset(lm, FINGERS[b][3])
    swapped = knuckle_order * tip_order < 0 and abs(tip_order) >= CROSS_MIN_SWAP * scale
    close = _dist(lm[FINGERS[a][3]], lm[FINGERS[b][3]]) < CROSS_MAX_TIP_GAP * scale
    return swapped and close


def is_unlimited_void(lm: Sequence[Point], handedness: str = "") -> bool:
    """Gojo's Unlimited Void: index and middle extended and crossed, ring and pinky curled."""
    return (
        finger_extended(lm, "index")
        and finger_extended(lm, "middle")
        and finger_curled(lm, "ring")
        and finger_curled(lm, "pinky")
        and fingers_crossed(lm, "index", "middle")
    )


GESTURES: dict[str, Callable[[Sequence[Point], str], bool]] = {
    "unlimited_void": is_unlimited_void,
}
