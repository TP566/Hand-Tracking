import json
import math

import numpy as np
import pytest

from hand_signs import Hand
from learned_signs import MIN_SAMPLES, LearnedSigns, build_gestures, frame_features
from test_hand_signs import make_hand, transform

ALL = ("index", "middle", "ring", "pinky")


def sample(lm, rng, yaw=0.0, angle=0.0, scale=1.0, mirror=False, noise=1.5, offset=(320.0, 400.0)):
    """A recorded-looking hand: jittered image points plus matching world points."""
    base = [(-x if mirror else x, y) for x, y in lm]
    base = [(x + rng.uniform(-noise, noise), y + rng.uniform(-noise, noise)) for x, y in base]
    a = math.radians(yaw)
    world = [(x * math.cos(a) / 1000, y / 1000, x * math.sin(a) / 1000) for x, y in base]
    image = transform([(wx * 1000, wy * 1000) for wx, wy, _ in world], angle, False, scale, offset)
    return Hand(image=image, world=world, handedness="Left" if mirror else "Right")


def recordings(rng, n=40):
    vary = lambda: dict(yaw=rng.uniform(-15, 15), angle=rng.uniform(-20, 20), scale=rng.uniform(0.8, 1.2))
    return {
        "peace": [[sample(make_hand(), rng, **vary())] for _ in range(n)],
        "none": ([[sample(make_hand(extended=()), rng, **vary())] for _ in range(n)]
                 + [[sample(make_hand(extended=ALL), rng, **vary())] for _ in range(n)]),
    }


@pytest.fixture
def model():
    return LearnedSigns(recordings(np.random.default_rng(0)))


@pytest.mark.parametrize("angle", [-30, 0, 45])
@pytest.mark.parametrize("scale", [0.6, 1.5])
@pytest.mark.parametrize("mirror", [False, True])
def test_learned_sign_recognised_when_moved_scaled_mirrored(model, angle, scale, mirror):
    rng = np.random.default_rng(1)
    hand = sample(make_hand(), rng, angle=angle, scale=scale, mirror=mirror, offset=(900.0, 200.0))
    assert model.classify([hand]) == "peace"


def test_counter_examples_and_unrecorded_poses_rejected(model):
    rng = np.random.default_rng(2)
    assert model.classify([sample(make_hand(extended=()), rng)]) is None          # recorded as none
    assert model.classify([sample(make_hand(extended=("index",)), rng)]) is None  # never recorded
    assert model.classify([]) is None


def test_two_hand_sign_never_matches_one_hand():
    rng = np.random.default_rng(3)
    pair = lambda: [sample(make_hand(), rng, offset=(200.0, 400.0)), sample(make_hand(), rng, offset=(500.0, 400.0))]
    model = LearnedSigns({"double_peace": [pair() for _ in range(40)],
                          "none": [[sample(make_hand(extended=()), rng)] for _ in range(40)]})
    assert model.classify(pair()) == "double_peace"
    assert model.classify([sample(make_hand(), rng)]) is None


def test_two_hand_features_include_relative_position():
    rng = np.random.default_rng(4)
    a, b = sample(make_hand(), rng, offset=(200.0, 400.0)), sample(make_hand(), rng, offset=(500.0, 400.0))
    assert len(frame_features([a, b])) == 2 * len(frame_features([a])) + 2
    assert np.allclose(frame_features([a, b]), frame_features([b, a]))  # order of detection doesn't matter


def test_repeated_calls_on_same_frame_are_cached(model):
    hands = [sample(make_hand(), np.random.default_rng(5))]
    assert model.classify(hands) == "peace"
    model.groups.clear()  # would break a fresh classification
    assert model.classify(hands) == "peace"


def write_recordings(folder, label, frames):
    (folder / label).mkdir(parents=True)
    for i, hands in enumerate(frames):
        data = {"label": label, "width": 1280, "height": 720,
                "hands": [{"image": [list(p) for p in h.image], "world": [list(p) for p in h.world],
                           "handedness": h.handedness} for h in hands]}
        (folder / label / f"{i:04d}.json").write_text(json.dumps(data), encoding="utf-8")


def test_build_gestures_adds_learned_signs_and_skips_small_ones(tmp_path):
    rng = np.random.default_rng(6)
    recs = recordings(rng)
    for label, frames in recs.items():
        write_recordings(tmp_path, label, frames)
    write_recordings(tmp_path, "pointing", [[sample(make_hand(extended=("index",)), rng)]
                                            for _ in range(MIN_SAMPLES - 5)])
    rule = lambda hands: False
    gestures, messages = build_gestures(tmp_path, rules={"unlimited_void": rule})
    assert gestures["unlimited_void"] is rule
    assert "peace" in gestures and "none" not in gestures and "pointing" not in gestures
    assert any("pointing" in m and "5 more" in m for m in messages)
    assert gestures["peace"]([sample(make_hand(), rng)])
    assert not gestures["peace"]([sample(make_hand(extended=()), rng)])


def test_build_gestures_without_samples(tmp_path):
    rule = lambda hands: False
    gestures, messages = build_gestures(tmp_path / "missing", rules={"r": rule})
    assert gestures == {"r": rule} and messages == []
