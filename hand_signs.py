"""Rule-based hand sign detectors over MediaPipe hand landmarks.

Each detector takes the list of hands seen in the current frame and returns
``True`` when its sign is present. A ``Hand`` carries the 21 landmarks in image
pixels (y pointing down) and, when available, MediaPipe's 3D world landmarks
in metres, which keep finger geometry readable when the hand is seen edge-on.
"""

import math
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

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
# A "raised" finger (may be hooked) has its tip this much farther from the wrist than its MCP.
RAISED_RATIO = 1.25
# Crossed tips must be closer than this fraction of the palm length.
CROSS_MAX_TIP_GAP = 0.45
# Tips must be swapped by at least this fraction of the palm length (filters jitter
# when the two fingers are merely held together).
CROSS_MIN_SWAP = 0.03
CROSS_MIN_SWAP_3D = 0.03

# On real hands MediaPipe rarely places crossed tips fully swapped. Tuned on the
# recorded samples: the index tip lines up with (or passes) the middle tip in the
# image, and in 3D the index leans in towards the middle finger.
# Max lead of the index tip over the middle tip across the palm (fraction of palm length).
CROSS_TIP_LEAD_MAX = 0.03
# The index DIP must sit at least this far in from the index knuckle, towards the
# middle finger (fraction of palm length; negative = leaning in).
INDEX_LEAN_MAX = -0.01

# Malevolent Shrine: both hands point up within this angle of vertical...
SHRINE_MAX_TILT_DEG = 60.0
# ...an index or middle fingertip of each hand touch (fraction of mean palm length; in the
# recorded Shrines the median gap is 0.05, while tips held slightly apart start around 0.45)...
SHRINE_APEX_GAP = 0.35
# ...and the wrists are spread apart, unlike prayer hands. Ring and pinky are folded or
# interlocked, unlike two open hands touching at the fingertips.
SHRINE_MIN_WRIST_GAP = 0.75
# Unlimited Void is a one-hand sign: two raised hands with fingertips this close
# (fraction of palm length) are some two-hand pose, never a Void.
VOID_NEARBY_HAND_GAP = 1.0


@dataclass
class Hand:
    image: Sequence[Point]
    world: Optional[Sequence[Point]] = None
    handedness: str = ""


def _dist(a: Point, b: Point) -> float:
    return math.dist(a, b)


def _sub(a: Point, b: Point) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _dot(a: Point, b: Point) -> float:
    return sum(x * y for x, y in zip(a, b))


def _unit(v: Point) -> list[float]:
    n = math.sqrt(_dot(v, v)) or 1e-9
    return [x / n for x in v]


def _segment_dist(p: Point, a: Point, b: Point) -> float:
    ab, ap = _sub(b, a), _sub(p, a)
    t = max(0.0, min(1.0, _dot(ap, ab) / (_dot(ab, ab) or 1e-9)))
    return _dist(p, [x + t * d for x, d in zip(a, ab)])


def tips_close(lm: Sequence[Point], a: str, b: str, max_gap: float) -> bool:
    """Either finger's tip lies near the other finger's PIP-to-tip segment.

    Tip-to-tip distance is too strict for a hooked finger, which rests partway
    along the other one.
    """
    _, pip_a, _, tip_a = FINGERS[a]
    _, pip_b, _, tip_b = FINGERS[b]
    gap = min(_segment_dist(lm[tip_b], lm[pip_a], lm[tip_a]),
              _segment_dist(lm[tip_a], lm[pip_b], lm[tip_b]))
    return gap < max_gap


def palm_length(lm: Sequence[Point]) -> float:
    """Wrist to middle-finger MCP distance, used as the hand's size scale."""
    return _dist(lm[WRIST], lm[FINGERS["middle"][0]]) or 1e-6


# These finger tests use distances only, so they work on 2D image or 3D world points.
def finger_extended(lm: Sequence[Point], finger: str) -> bool:
    _, pip, _, tip = FINGERS[finger]
    return _dist(lm[WRIST], lm[tip]) > _dist(lm[WRIST], lm[pip]) * EXTENDED_RATIO


def finger_raised(lm: Sequence[Point], finger: str) -> bool:
    mcp, _, _, tip = FINGERS[finger]
    return _dist(lm[WRIST], lm[tip]) > _dist(lm[WRIST], lm[mcp]) * RAISED_RATIO


def finger_curled(lm: Sequence[Point], finger: str) -> bool:
    _, pip, _, tip = FINGERS[finger]
    return _dist(lm[WRIST], lm[tip]) < _dist(lm[WRIST], lm[pip])


def side_offset(lm: Sequence[Point], idx: int) -> float:
    """Signed distance of a landmark across the palm, in a hand-local 2D frame.

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
    return swapped and tips_close(lm, a, b, CROSS_MAX_TIP_GAP * scale)


def palm_across_axis(world: Sequence[Point]) -> list[float]:
    """Unit vector across the palm (pinky MCP to index MCP), perpendicular to wrist->middle MCP."""
    up = _unit(_sub(world[FINGERS["middle"][0]], world[WRIST]))
    across = _sub(world[FINGERS["index"][0]], world[FINGERS["pinky"][0]])
    across = _sub(across, [u * _dot(across, up) for u in up])
    return _unit(across)


def fingers_crossed_3d(world: Sequence[Point], a: str = "index", b: str = "middle") -> bool:
    """3D version of ``fingers_crossed``: compares order along the palm's across axis.

    Because MediaPipe estimates depth, this still works when the hand is seen
    edge-on and the two fingers overlap in the image.
    """
    scale = palm_length(world)
    across = palm_across_axis(world)
    knuckle_order = _dot(_sub(world[FINGERS[a][0]], world[FINGERS[b][0]]), across)
    tip_order = _dot(_sub(world[FINGERS[a][3]], world[FINGERS[b][3]]), across)
    swapped = knuckle_order * tip_order < 0 and abs(tip_order) >= CROSS_MIN_SWAP_3D * scale
    return swapped and tips_close(world, a, b, CROSS_MAX_TIP_GAP * scale)


def index_side_offset(lm: Sequence[Point], idx: int) -> float:
    """``side_offset`` as a fraction of palm length, positive towards the index side.

    Oriented by the index and pinky knuckles, which stay further apart than the
    index and middle ones when the hand turns sideways.
    """
    sign = 1.0 if side_offset(lm, FINGERS["index"][0]) >= side_offset(lm, FINGERS["pinky"][0]) else -1.0
    return sign * side_offset(lm, idx) / palm_length(lm)


def tips_aligned(lm: Sequence[Point]) -> bool:
    """2D: the index tip does not lead the middle tip towards the index side, and they touch."""
    lead = index_side_offset(lm, FINGERS["index"][3]) - index_side_offset(lm, FINGERS["middle"][3])
    return lead < CROSS_TIP_LEAD_MAX and tips_close(lm, "index", "middle", CROSS_MAX_TIP_GAP * palm_length(lm))


def index_leans_in(world: Sequence[Point]) -> bool:
    """3D: the index finger is pushed across towards the middle finger."""
    mcp, _, dip, _ = FINGERS["index"]
    return _dot(_sub(world[dip], world[mcp]), palm_across_axis(world)) / palm_length(world) < INDEX_LEAN_MAX


def _void_shape(lm: Sequence[Point]) -> bool:
    # The middle finger only has to be raised: from the side it hooks over the index.
    return (finger_extended(lm, "index") and finger_raised(lm, "middle")
            and finger_curled(lm, "ring") and finger_curled(lm, "pinky"))


def is_unlimited_void(hands: Sequence[Hand]) -> bool:
    """Gojo's Unlimited Void: index up, middle crossed over it, ring and pinky curled."""
    if _shrine_apex(hands, VOID_NEARBY_HAND_GAP) is not None:
        return False  # a two-hand pose; interlocked or side-by-side fingers can look crossed
    for hand in hands:
        shape = _void_shape(hand.image) or (hand.world is not None and _void_shape(hand.world))
        if hand.world is not None:
            crossed = tips_aligned(hand.image) and index_leans_in(hand.world)
        else:
            crossed = fingers_crossed(hand.image)
        if shape and crossed:
            return True
    return False


def _pointing_up(lm: Sequence[Point]) -> bool:
    ux, uy = _sub(lm[FINGERS["middle"][0]], lm[WRIST])[:2]
    norm = math.hypot(ux, uy) or 1e-6
    return -uy / norm >= math.cos(math.radians(SHRINE_MAX_TILT_DEG))


def _shrine_apex(hands: Sequence[Hand], max_gap: float) -> Optional[tuple[float, int, int]]:
    """(mean palm length, tip of a, tip of b) when two upright hands' fingertips are within ``max_gap``."""
    if len(hands) != 2:
        return None
    a, b = hands[0].image, hands[1].image
    if not (_pointing_up(a) and _pointing_up(b)):
        return None
    scale = (palm_length(a) + palm_length(b)) / 2
    tips = (FINGERS["index"][3], FINGERS["middle"][3])
    gap, ta, tb = min((_dist(a[i], b[j]), i, j) for i in tips for j in tips)
    return (scale, ta, tb) if gap < max_gap * scale else None


def _outer_fingers_folded(lm: Sequence[Point]) -> bool:
    return not (finger_extended(lm, "ring") and finger_extended(lm, "pinky"))


def is_malevolent_shrine(hands: Sequence[Hand]) -> bool:
    """Sukuna's Malevolent Shrine: two upright hands meeting at the fingertips in an "A" shape."""
    apex = _shrine_apex(hands, SHRINE_APEX_GAP)
    if apex is None:
        return False
    scale, ta, tb = apex
    a, b = hands[0].image, hands[1].image
    apex_y = (a[ta][1] + b[tb][1]) / 2
    wrists_apart = _dist(a[WRIST], b[WRIST]) > SHRINE_MIN_WRIST_GAP * scale
    apex_above = apex_y < min(a[WRIST][1], b[WRIST][1]) - 0.5 * scale
    folded = _outer_fingers_folded(a) and _outer_fingers_folded(b)
    return wrists_apart and apex_above and folded


GESTURES: dict[str, Callable[[Sequence[Hand]], bool]] = {
    "unlimited_void": is_unlimited_void,
    "malevolent_shrine": is_malevolent_shrine,
}
