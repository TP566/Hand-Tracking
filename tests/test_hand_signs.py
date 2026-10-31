import math

import pytest

from hand_signs import GESTURES, fingers_crossed, is_unlimited_void

# Knuckle x positions for an upright hand, wrist at the origin, y pointing down.
KNUCKLE_X = {"index": -30.0, "middle": -10.0, "ring": 10.0, "pinky": 30.0}
EXTENDED = [(0, -40), (0, -65), (0, -90)]  # PIP, DIP, TIP offsets from the MCP
CURLED = [(0, -35), (0, -20), (0, -5)]


def make_hand(extended=("index", "middle"), tip_x=None):
    """Build 21 landmarks; ``tip_x`` overrides a finger's DIP/TIP x position."""
    tip_x = tip_x or {}
    lm = [(0.0, 0.0)] + [(-40.0, -30.0 - 15 * i) for i in range(4)]  # wrist + thumb
    for finger in ("index", "middle", "ring", "pinky"):
        mx, my = KNUCKLE_X[finger], -100.0
        lm.append((mx, my))
        offsets = EXTENDED if finger in extended else CURLED
        for j, (dx, dy) in enumerate(offsets):
            x = mx + dx
            if finger in tip_x and j >= 1:
                x = tip_x[finger] if j == 2 else (mx + tip_x[finger]) / 2
            lm.append((x, my + dy))
    return lm


def crossed_hand():
    return make_hand(tip_x={"index": -5.0, "middle": -35.0})


def transform(lm, angle_deg=0.0, mirror=False, scale=1.0, offset=(320.0, 400.0)):
    a = math.radians(angle_deg)
    out = []
    for x, y in lm:
        if mirror:
            x = -x
        rx = x * math.cos(a) - y * math.sin(a)
        ry = x * math.sin(a) + y * math.cos(a)
        out.append((rx * scale + offset[0], ry * scale + offset[1]))
    return out


def test_crossed_fingers_detected():
    assert is_unlimited_void(crossed_hand())


def test_peace_sign_not_detected():
    assert not is_unlimited_void(make_hand())


def test_fingers_together_not_detected():
    together = make_hand(tip_x={"index": -21.0, "middle": -19.0})
    assert not is_unlimited_void(together)


def test_fist_not_detected():
    assert not is_unlimited_void(make_hand(extended=(), tip_x={"index": -5.0, "middle": -35.0}))


def test_open_hand_not_detected():
    open_hand = make_hand(extended=("index", "middle", "ring", "pinky"),
                          tip_x={"index": -5.0, "middle": -35.0})
    assert not is_unlimited_void(open_hand)


def test_crossed_but_far_apart_not_detected():
    assert not fingers_crossed(make_hand(tip_x={"index": 40.0, "middle": -80.0}))


@pytest.mark.parametrize("angle", [-60, -30, 0, 30, 60, 180])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("scale", [0.5, 2.0])
def test_detection_invariant_to_rotation_hand_and_size(angle, mirror, scale):
    assert is_unlimited_void(transform(crossed_hand(), angle, mirror, scale))
    assert not is_unlimited_void(transform(make_hand(), angle, mirror, scale))


def test_registry_contains_unlimited_void():
    assert GESTURES["unlimited_void"] is is_unlimited_void
