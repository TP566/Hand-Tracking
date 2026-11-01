"""Recorded real-hand samples must be recognised well enough to trigger reliably.

Single frames can't all be right: recordings include transitions, and pressed-together
Shrine hands are often seen as one hand. So these tests check per-label detection
rates, and replay each recording through ``HoldTrigger`` as the app would.
"""

import json
from pathlib import Path

import pytest

from gesture_trigger import HoldTrigger
from hand_signs import GESTURES, Hand

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
LABELS = ("unlimited_void", "malevolent_shrine", "none")
FRAMES_PER_SAMPLE = 3  # the recorder saves every 3rd frame

# Minimum share of a sign's frames it is detected in.
MIN_RECALL = {"unlimited_void": 0.70, "malevolent_shrine": 0.40}
# Minimum share of two-hand Shrine frames it is detected in.
MIN_SHRINE_TWO_HAND_RECALL = 0.80
# Maximum share of frames where a sign is detected in someone else's recording.
MAX_FALSE_RATE = 0.05


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Hand(image=[tuple(p) for p in h["image"]],
                 world=[tuple(p) for p in h["world"]] if h.get("world") else None,
                 handedness=h.get("handedness", "")) for h in data["hands"]]


RECORDINGS = {label: [load(p) for p in sorted((SAMPLES / label).glob("*.json"))] for label in LABELS}
pytestmark = pytest.mark.skipif(not any(RECORDINGS.values()), reason="no recorded samples yet")


def rate(label, sign, frames=None):
    frames = RECORDINGS[label] if frames is None else frames
    return sum(GESTURES[sign](hands) for hands in frames) / max(1, len(frames))


def trigger_fires(label, sign):
    t = [0.0]
    trigger = HoldTrigger(12, 1.5, 3, clock=lambda: t[0])
    fires = 0
    for hands in RECORDINGS[label]:
        detected = GESTURES[sign](hands)
        for _ in range(FRAMES_PER_SAMPLE):
            t[0] += 1 / 30
            fires += trigger.update(detected)
    return fires


@pytest.mark.parametrize("sign", MIN_RECALL)
def test_sign_detected_in_its_recordings(sign):
    if not RECORDINGS[sign]:
        pytest.skip(f"no {sign} samples")
    assert rate(sign, sign) >= MIN_RECALL[sign]
    assert trigger_fires(sign, sign) >= 1


def test_shrine_detected_when_both_hands_seen():
    two_hand = [h for h in RECORDINGS["malevolent_shrine"] if len(h) == 2]
    if not two_hand:
        pytest.skip("no two-hand Shrine samples")
    assert rate("malevolent_shrine", "malevolent_shrine", two_hand) >= MIN_SHRINE_TWO_HAND_RECALL


@pytest.mark.parametrize("label,sign", [(label, sign) for label in LABELS for sign in GESTURES if sign != label])
def test_sign_not_triggered_by_other_recordings(label, sign):
    if not RECORDINGS[label]:
        pytest.skip(f"no {label} samples")
    assert rate(label, sign) <= MAX_FALSE_RATE
    assert trigger_fires(label, sign) == 0
