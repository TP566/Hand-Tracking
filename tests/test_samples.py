"""Every recorded real-hand sample must be classified as its label."""

import json
from pathlib import Path

import pytest

from hand_signs import GESTURES, Hand

SAMPLES = sorted((Path(__file__).resolve().parent.parent / "samples").glob("*/*.json"))


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    hands = [Hand(image=[tuple(p) for p in h["image"]],
                  world=[tuple(p) for p in h["world"]] if h.get("world") else None,
                  handedness=h.get("handedness", "")) for h in data["hands"]]
    return data["label"], hands


@pytest.mark.skipif(not SAMPLES, reason="no recorded samples yet")
@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_sample_classified_as_label(path):
    label, hands = load(path)
    detected = {name for name, fn in GESTURES.items() if fn(hands)}
    expected = set() if label == "none" else {label}
    assert detected == expected
