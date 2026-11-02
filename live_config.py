"""Pick up config.json edits while the app runs, with no GUI in it.

``ConfigWatcher`` notices a changed file and hands back its content only when the
whole file is valid. ``apply_live`` then pushes the settings that can change
mid-call (``config_store.LIVE_KEYS``) into the running objects, and reports the
rest as needing a restart.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import actions as pc_actions
import config_store
from gesture_trigger import HoldTrigger
from pipeline import QualityGovernor

# What main.py assumes when a live key is missing from config.json.
DEFAULTS = {"miss_tolerance": 3, "quality": "auto", "show_preview": True,
            "preview_width": 640, "mirror_preview": True, "actions": {}}
PREVIEW_KEYS = ("show_preview", "preview_width", "mirror_preview")
TRIGGER_KEYS = ("hold_frames", "miss_tolerance", "cooldown_sec")


@dataclass
class LiveResult:
    applied: list[str] = field(default_factory=list)    # live keys whose value changed
    restart: list[str] = field(default_factory=list)    # changed keys that need a restart
    warnings: list[str] = field(default_factory=list)
    preview: dict = field(default_factory=dict)          # show_preview, preview_width, mirror_preview
    quality_changed: bool = False                        # the governor's level moved


class ConfigWatcher:
    """Polls a config file's modification time and returns its content once per valid change."""

    def __init__(self, path: Path, interval_sec: float = 1.0,
                 clock: Callable[[], float] = time.monotonic):
        self.path = path
        self.interval = interval_sec
        self.clock = clock
        self._last_check = clock()
        self._seen_mtime = self._mtime()

    def _mtime(self) -> Optional[float]:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return None

    def _reject(self, reason: str) -> None:
        print(f"{self.path.name}: {reason}; keeping current settings")

    def poll(self) -> Optional[dict]:
        """The new config when the file changed and is valid; None otherwise.

        A bad file is reported once and then ignored until it changes again. The
        mtime is read before the file, so a write landing in between is seen next poll.
        """
        now = self.clock()
        if now - self._last_check < self.interval:
            return None
        self._last_check = now
        mtime = self._mtime()
        if mtime is None or mtime == self._seen_mtime:
            return None
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None     # mid-replace or locked: try again on the next poll
        self._seen_mtime = mtime
        try:
            cfg = json.loads(text)
        except ValueError as exc:
            self._reject(f"not valid JSON ({exc})")
            return None
        if not isinstance(cfg, dict):
            self._reject("must be a JSON object")
            return None
        errors = config_store.validate(cfg)
        if errors:
            field_path, message = next(iter(errors.items()))
            self._reject(f"{field_path}: {message}")
            return None
        return cfg


def _value(cfg: dict, key: str):
    return cfg.get(key, DEFAULTS.get(key))


def apply_live(old: dict, new: dict, triggers: dict[str, HoldTrigger], governor: QualityGovernor,
               actions: pc_actions.Actions) -> LiveResult:
    """Apply the live settings of ``new`` that differ from ``old`` to the running objects."""
    result = LiveResult()
    result.preview = {key: _value(new, key) for key in PREVIEW_KEYS}
    for key in config_store.LIVE_KEYS:
        if _value(old, key) == _value(new, key):
            continue
        if key in TRIGGER_KEYS:
            for trigger in triggers.values():
                setattr(trigger, key, _value(new, key))
        elif key == "quality":
            result.quality_changed = governor.set_mode(_value(new, key))
        elif key == "actions":
            try:
                actions.actions = pc_actions.validate(_value(new, key), new.get("domains", {}))
            except SystemExit as exc:
                result.warnings.append(f"{exc}; keeping the current actions")
                continue
        result.applied.append(key)

    keys = list(old) + [key for key in new if key not in old]
    result.restart = [key for key in keys
                      if key not in config_store.LIVE_KEYS and old.get(key) != new.get(key)]
    return result
