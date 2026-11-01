import math

import pytest

from hand_signs import (GESTURES, Hand, fingers_crossed, fingers_crossed_3d, is_malevolent_shrine,
                        is_unlimited_void)

# Knuckle x positions for an upright hand, wrist at the origin, y pointing down.
KNUCKLE_X = {"index": -30.0, "middle": -10.0, "ring": 10.0, "pinky": 30.0}
EXTENDED = [(0, -40), (0, -65), (0, -90)]  # PIP, DIP, TIP offsets from the MCP
CURLED = [(0, -35), (0, -20), (0, -5)]
HOOKED = [(0, -40), (0, -55), (0, -50)]  # bent at the last joints, tip still well above the knuckle


def make_hand(extended=("index", "middle"), tip_x=None, hooked=()):
    """Build 21 landmarks; ``tip_x`` overrides a finger's DIP/TIP x position."""
    tip_x = tip_x or {}
    # Wrist sits under the middle knuckle, as on a real hand.
    lm = [(KNUCKLE_X["middle"], 0.0)] + [(-40.0, -30.0 - 15 * i) for i in range(4)]  # wrist + thumb
    for finger in ("index", "middle", "ring", "pinky"):
        mx, my = KNUCKLE_X[finger], -100.0
        lm.append((mx, my))
        offsets = HOOKED if finger in hooked else EXTENDED if finger in extended else CURLED
        for j, (dx, dy) in enumerate(offsets):
            x = mx + dx
            if finger in tip_x and j >= 1:
                x = tip_x[finger] if j == 2 else (mx + tip_x[finger]) / 2
            lm.append((x, my + dy))
    return lm


def crossed_hand(**kw):
    return make_hand(tip_x={"index": -5.0, "middle": -35.0}, **kw)


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


def edge_on(lm, yaw_deg=90.0):
    """Turn a flat hand about the vertical axis: returns (image points, world points in metres)."""
    a = math.radians(yaw_deg)
    world = [(x * math.cos(a) / 1000, y / 1000, x * math.sin(a) / 1000) for x, y in lm]
    image = [(320 + wx * 1000, 400 + wy * 1000) for wx, wy, _ in world]
    return image, world


def hand(lm):
    return [Hand(image=lm)]


# --- Unlimited Void ---------------------------------------------------------

def test_crossed_fingers_detected():
    assert is_unlimited_void(hand(crossed_hand()))


def test_peace_sign_not_detected():
    assert not is_unlimited_void(hand(make_hand()))


def test_fingers_together_not_detected():
    assert not is_unlimited_void(hand(make_hand(tip_x={"index": -21.0, "middle": -19.0})))


def test_fist_not_detected():
    assert not is_unlimited_void(hand(make_hand(extended=(), tip_x={"index": -5.0, "middle": -35.0})))


def test_open_hand_not_detected():
    open_hand = make_hand(extended=("index", "middle", "ring", "pinky"),
                          tip_x={"index": -5.0, "middle": -35.0})
    assert not is_unlimited_void(hand(open_hand))


def test_crossed_but_far_apart_not_detected():
    assert not fingers_crossed(make_hand(tip_x={"index": 40.0, "middle": -80.0}))


def test_hooked_middle_finger_detected():
    assert is_unlimited_void(hand(crossed_hand(extended=("index",), hooked=("middle",))))


@pytest.mark.parametrize("angle", [-60, -30, 0, 30, 60, 180])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("scale", [0.5, 2.0])
def test_detection_invariant_to_rotation_hand_and_size(angle, mirror, scale):
    assert is_unlimited_void(hand(transform(crossed_hand(), angle, mirror, scale)))
    assert not is_unlimited_void(hand(transform(make_hand(), angle, mirror, scale)))


@pytest.mark.parametrize("yaw", [70, 90, -90])
def test_edge_on_crossed_detected_via_3d(yaw):
    image, world = edge_on(crossed_hand(), yaw)
    if abs(yaw) == 90:
        assert not fingers_crossed(image)  # fully edge-on, the 2D view cannot see the crossing
    assert fingers_crossed_3d(world)
    assert is_unlimited_void([Hand(image=image, world=world)])


@pytest.mark.parametrize("yaw", [70, 90, -90])
def test_edge_on_uncrossed_not_detected(yaw):
    image, world = edge_on(make_hand(), yaw)
    assert not is_unlimited_void([Hand(image=image, world=world)])


# --- Malevolent Shrine ------------------------------------------------------

def shrine_pair(tilt_deg=30.0, apex_gap=2.0, flip=False):
    """Two open hands leaning towards each other so their middle tips meet at an apex."""
    base = make_hand(extended=("index", "middle", "ring", "pinky"))
    apex = (320.0, 150.0)
    hands = []
    for side in (-1, 1):
        lm = transform(base, angle_deg=side * tilt_deg, mirror=side > 0, offset=(0.0, 0.0))
        if flip:
            lm = [(x, -y) for x, y in lm]
        tx, ty = lm[12]
        dx = apex[0] - tx + side * apex_gap / 2
        dy = apex[1] - ty
        hands.append(Hand(image=[(x + dx, y + dy) for x, y in lm]))
    return hands


def test_shrine_a_shape_detected():
    assert is_malevolent_shrine(shrine_pair())


@pytest.mark.parametrize("tilt", [20, 30, 45])
def test_shrine_detected_across_tilts(tilt):
    assert is_malevolent_shrine(shrine_pair(tilt_deg=tilt))


def test_prayer_hands_not_shrine():
    assert not is_malevolent_shrine(shrine_pair(tilt_deg=2))


def test_single_hand_not_shrine():
    assert not is_malevolent_shrine(shrine_pair()[:1])


def test_hands_apart_not_shrine():
    assert not is_malevolent_shrine(shrine_pair(apex_gap=200))


def test_hands_pointing_down_not_shrine():
    assert not is_malevolent_shrine(shrine_pair(flip=True))


def test_shrine_is_not_unlimited_void():
    assert not is_unlimited_void(shrine_pair())


def test_registry_contains_both_signs():
    assert GESTURES["unlimited_void"] is is_unlimited_void
    assert GESTURES["malevolent_shrine"] is is_malevolent_shrine
