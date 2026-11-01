"""Signs learned from recordings instead of hand-written rules.

Record a new sign with ``teach.bat <name>`` and it is recognised by comparing
each frame with the recordings in ``samples/`` (k-nearest neighbours). The
``none`` recordings and the other signs' recordings act as counter-examples,
so a pose is only claimed by the sign it most resembles.
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from hand_signs import FINGERS, GESTURES, WRIST, Hand

# A learned sign needs at least this many recorded frames.
MIN_SAMPLES = 30
# Nearest recordings compared per frame, and how many of them must agree. Unanimous
# votes halved false alarms on the real recordings at little cost in detection.
K = 5
MIN_VOTES = 5
# A frame further from its sign's recordings than this multiple of their own
# typical spread is rejected as unlike anything recorded.
RADIUS_SCALE = 1.5
NONE_LABEL = "none"
# Built-in signs also recognised from their recordings (rule OR recordings). The Shrine's
# rule misses frames where the pressed hands merge; on held-out recordings the combination
# caught 93% of Shrine frames (rule alone 49%) with no false alarms. Unlimited Void stays
# rule-only: learned, it confused crossed with side-by-side fingers too often.
COMBINED_SIGNS = ("malevolent_shrine",)
SIGN_NAME = re.compile(r"^[A-Za-z0-9_]+$")

INDEX_MCP, MIDDLE_MCP, PINKY_MCP = FINGERS["index"][0], FINGERS["middle"][0], FINGERS["pinky"][0]


def load_sample(path: Path) -> list[Hand]:
    """Hands from one recorder JSON file (see ``record_samples.save_sample``)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Hand(image=[tuple(p) for p in h["image"]],
                 world=[tuple(p) for p in h["world"]] if h.get("world") else None,
                 handedness=h.get("handedness", "")) for h in data["hands"]]


def load_samples(samples_dir: Path) -> dict[str, list[list[Hand]]]:
    """Recordings per label folder, in time order."""
    if not samples_dir.exists():
        return {}
    return {folder.name: [load_sample(p) for p in sorted(folder.glob("*.json"))]
            for folder in sorted(samples_dir.iterdir()) if folder.is_dir() and any(folder.glob("*.json"))}


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) or 1e-9)


def hand_features(hand: Hand) -> np.ndarray:
    """Landmarks in the hand's own frame: independent of position, size, rotation and which hand.

    Image points use a 2D frame (wrist origin, wrist->middle knuckle up, index side +x);
    world points use the 3D palm frame, with the palm normal flipped for left hands.
    """
    im = np.asarray(hand.image, float)[:, :2]
    up = im[MIDDLE_MCP] - im[WRIST]
    scale = np.linalg.norm(up) or 1e-6
    up = up / scale
    across = np.array([-up[1], up[0]])
    if (im[INDEX_MCP] - im[PINKY_MCP]) @ across < 0:
        across = -across
    image_part = ((im - im[WRIST]) @ np.stack([across, up]).T / scale).ravel()

    if hand.world is None:
        return np.concatenate([image_part, np.zeros(63)])
    w = np.asarray(hand.world, float)
    up3 = w[MIDDLE_MCP] - w[WRIST]
    scale3 = np.linalg.norm(up3) or 1e-6
    up3 = up3 / scale3
    across3 = w[INDEX_MCP] - w[PINKY_MCP]
    across3 = _unit(across3 - up3 * (across3 @ up3))
    normal = np.cross(up3, across3)
    if hand.handedness == "Left":
        normal = -normal
    world_part = ((w - w[WRIST]) @ np.stack([across3, up3, normal]).T / scale3).ravel()
    return np.concatenate([image_part, world_part])


def frame_features(hands: Sequence[Hand]) -> np.ndarray:
    """Features of every hand (left to right in the image), plus where the hands are relative to each other."""
    ordered = sorted(hands, key=lambda h: h.image[WRIST][0])
    parts = [hand_features(h) for h in ordered]
    if len(ordered) > 1:
        a, b = (np.asarray(h.image, float)[:, :2] for h in ordered[:2])
        scale = (np.linalg.norm(a[MIDDLE_MCP] - a[WRIST]) + np.linalg.norm(b[MIDDLE_MCP] - b[WRIST])) / 2 or 1e-6
        parts.append((b[WRIST] - a[WRIST]) / scale)
    return np.concatenate(parts)


class LearnedSigns:
    """k-nearest-neighbour classifier over recorded frames, grouped by number of hands."""

    def __init__(self, recordings: dict[str, list[list[Hand]]]):
        self.labels = sorted(recordings)
        self.groups: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self.radius: dict[tuple[int, str], float] = {}
        by_count: dict[int, tuple[list, list]] = {}
        for label, frames in recordings.items():
            for hands in frames:
                if hands:
                    xs, ys = by_count.setdefault(len(hands), ([], []))
                    xs.append(frame_features(hands))
                    ys.append(label)
        for count, (xs, ys) in by_count.items():
            X, y = np.stack(xs), np.array(ys)
            self.groups[count] = (X, y)
            for label in set(ys) - {NONE_LABEL}:
                own = X[y == label]
                if len(own) <= K:
                    continue
                d = np.linalg.norm(own[:, None, :] - own[None, :, :], axis=2)
                np.fill_diagonal(d, np.inf)
                spread = np.sort(d, axis=1)[:, :K].mean(axis=1)
                self.radius[(count, label)] = float(np.percentile(spread, 95)) * RADIUS_SCALE
        self._last_hands: Optional[Sequence[Hand]] = None
        self._last_result: Optional[str] = None

    def classify(self, hands: Sequence[Hand]) -> Optional[str]:
        """The recorded sign these hands show, or None. Cached for repeated calls on the same frame."""
        if hands is self._last_hands:
            return self._last_result
        result = None
        group = self.groups.get(len(hands))
        if hands and group is not None:
            X, y = group
            d = np.linalg.norm(X - frame_features(hands), axis=1)
            nearest = np.argsort(d)[:K]
            label, votes = Counter(y[nearest]).most_common(1)[0]
            radius = self.radius.get((len(hands), label))
            if (label != NONE_LABEL and votes >= min(MIN_VOTES, len(nearest)) and radius is not None
                    and d[nearest][y[nearest] == label].mean() <= radius):
                result = str(label)
        self._last_hands, self._last_result = hands, result
        return result

    def detector(self, label: str) -> Callable[[Sequence[Hand]], bool]:
        return lambda hands: self.classify(hands) == label


def _either(rule: Callable, learned: Callable) -> Callable[[Sequence[Hand]], bool]:
    return lambda hands: rule(hands) or learned(hands)


def build_gestures(samples_dir: Path, rules: Optional[dict] = None,
                   combined: Sequence[str] = COMBINED_SIGNS) -> tuple[dict[str, Callable], list[str]]:
    """Rule-based signs plus a learned detector for every other recorded sign.

    Signs in ``combined`` keep their rule and are also recognised from their recordings.
    Returns the detectors and messages about signs that need more recordings.
    """
    rules = GESTURES if rules is None else rules
    gestures = dict(rules)
    messages = []
    recordings = load_samples(samples_dir)
    learned = []
    for label, frames in recordings.items():
        if label == NONE_LABEL or not SIGN_NAME.match(label) or (label in rules and label not in combined):
            continue
        if len(frames) < MIN_SAMPLES:
            if label not in rules:
                messages.append(f"[{label}] {len(frames)} recorded frames; record at least "
                                f"{MIN_SAMPLES - len(frames)} more with teach.bat {label} to use this sign.")
            continue
        learned.append(label)
    if learned:
        model = LearnedSigns(recordings)
        for label in learned:
            detector = model.detector(label)
            gestures[label] = _either(rules[label], detector) if label in rules else detector
    return gestures, messages
