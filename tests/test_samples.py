"""Recorded real-hand samples must be recognised well enough to trigger reliably.

Single frames can't all be right: recordings include transitions, and pressed-together
Shrine hands are often seen as one hand. So these tests check per-label detection
rates, and replay each recording through ``HoldTrigger`` as the app would.

Built-in signs are checked with their rules. Taught signs are learned from the first
half of every label's recordings and checked on the second half, so their score
reflects new frames rather than memorised ones.

"none" recordings are the most valuable: look-alike poses recorded there (two open
hands touching at the fingertips, two hands side by side) shaped the current rules.
"""

from pathlib import Path

import pytest

from gesture_trigger import HoldTrigger
from hand_signs import GESTURES
from learned_signs import MIN_SAMPLES, NONE_LABEL, LearnedSigns, load_samples

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
FRAMES_PER_SAMPLE = 3  # the recorder saves every 3rd frame

# Minimum share of a sign's frames it is detected in.
MIN_RECALL = {"unlimited_void": 0.70, "malevolent_shrine": 0.50}
MIN_LEARNED_RECALL = 0.60
# Minimum share of two-hand Shrine frames it is detected in.
MIN_SHRINE_TWO_HAND_RECALL = 0.70
# Maximum share of frames where a sign is detected in someone else's recording.
MAX_FALSE_RATE = 0.05

RECORDINGS = load_samples(SAMPLES)
for _label in ("unlimited_void", "malevolent_shrine", NONE_LABEL):
    RECORDINGS.setdefault(_label, [])
pytestmark = pytest.mark.skipif(not any(RECORDINGS.values()), reason="no recorded samples yet")

LEARNED = sorted(label for label, frames in RECORDINGS.items()
                 if label not in GESTURES and label != NONE_LABEL and len(frames) >= 2 * MIN_SAMPLES)
TRAIN = {label: frames[:len(frames) // 2] for label, frames in RECORDINGS.items()}
TEST = {label: frames[len(frames) // 2:] for label, frames in RECORDINGS.items()}
MODEL = LearnedSigns(TRAIN)


def rate(detect, frames):
    return sum(detect(hands) for hands in frames) / max(1, len(frames))


def trigger_fires(detect, frames):
    t = [0.0]
    trigger = HoldTrigger(12, 1.5, 3, clock=lambda: t[0])
    fires = 0
    for hands in frames:
        detected = detect(hands)
        for _ in range(FRAMES_PER_SAMPLE):
            t[0] += 1 / 30
            fires += trigger.update(detected)
    return fires


@pytest.mark.parametrize("sign", MIN_RECALL)
def test_sign_detected_in_its_recordings(sign):
    if not RECORDINGS[sign]:
        pytest.skip(f"no {sign} samples")
    assert rate(GESTURES[sign], RECORDINGS[sign]) >= MIN_RECALL[sign]
    assert trigger_fires(GESTURES[sign], RECORDINGS[sign]) >= 1


def test_shrine_rule_detected_when_both_hands_seen():
    two_hand = [h for h in RECORDINGS["malevolent_shrine"] if len(h) == 2]
    if not two_hand:
        pytest.skip("no two-hand Shrine samples")
    assert rate(GESTURES["malevolent_shrine"], two_hand) >= MIN_SHRINE_TWO_HAND_RECALL


@pytest.mark.parametrize("label,sign", [(label, sign) for label in RECORDINGS for sign in GESTURES if sign != label])
def test_sign_not_triggered_by_other_recordings(label, sign):
    if not RECORDINGS[label]:
        pytest.skip(f"no {label} samples")
    assert rate(GESTURES[sign], RECORDINGS[label]) <= MAX_FALSE_RATE
    assert trigger_fires(GESTURES[sign], RECORDINGS[label]) == 0


def test_single_hand_never_taken_for_shrine():
    # Regression: one raised hand once opened the Shrine (through its stray one-hand frames).
    detect = GESTURES["malevolent_shrine"]
    singles = [[h] for label, frames in RECORDINGS.items() for hands in frames for h in hands
               if not (label == "malevolent_shrine" and len(hands) == 1)]
    if not singles:
        pytest.skip("no samples")
    assert rate(detect, singles) <= 0.01


@pytest.mark.skipif(not LEARNED, reason="no taught signs with enough recordings")
@pytest.mark.parametrize("sign", LEARNED)
def test_learned_sign_detected_in_new_frames(sign):
    detect = MODEL.detector(sign)
    assert rate(detect, TEST[sign]) >= MIN_LEARNED_RECALL
    assert trigger_fires(detect, TEST[sign]) >= 1


@pytest.mark.skipif(not LEARNED, reason="no taught signs with enough recordings")
@pytest.mark.parametrize("label,sign", [(label, sign) for label in RECORDINGS for sign in LEARNED if sign != label])
def test_learned_sign_not_triggered_by_other_recordings(label, sign):
    if not TEST[label]:
        pytest.skip(f"no {label} samples")
    detect = MODEL.detector(sign)
    assert rate(detect, TEST[label]) <= MAX_FALSE_RATE
    assert trigger_fires(detect, TEST[label]) == 0
