"""Settings model for config.json: load, validate and save, with no GUI in it.

The settings window and the live-reload watcher both go through here, so the
rules for what a valid config looks like live in one place. Saving is atomic
and keeps the previous file as ``config.json.bak``; keys this module does not
know about are written back untouched.
"""

import copy
import json
import os
import shutil
from pathlib import Path

from pynput.keyboard import HotKey

from actions import ACTION_TYPES
from hand_signs import GESTURES
from learned_signs import NONE_LABEL, SIGN_NAME

RANGES: dict[str, tuple[float, float]] = {
    "camera_index": (0, 10),
    "width": (160, 3840),
    "height": (120, 2160),
    "camera_fps": (1, 120),
    "fps": (1, 60),
    "hold_frames": (1, 120),
    "miss_tolerance": (0, 30),
    "cooldown_sec": (0, 10),
    "preview_width": (160, 1920),
}
INTEGER_KEYS = ("hold_frames", "miss_tolerance", "camera_index", "width", "height", "fps")
# Settings the running app can pick up without a restart.
LIVE_KEYS = ("hold_frames", "miss_tolerance", "cooldown_sec", "quality",
             "show_preview", "preview_width", "mirror_preview", "actions")
QUALITIES = ("auto", "high", "low")
# main.py reads these without a default, so a config without them cannot start.
REQUIRED_KEYS = ("camera_index", "width", "height", "fps", "hold_frames", "cooldown_sec")


class ConfigChanged(Exception):
    """config.json was modified by someone else after it was loaded."""


class RenameError(Exception):
    """A sign could not be renamed; the message says why, in words for the user."""


def load(path: Path) -> tuple[dict, float]:
    """The config and the file's modification time, for ``save``'s change check."""
    mtime = path.stat().st_mtime
    return json.loads(path.read_text(encoding="utf-8")), mtime


def save(path: Path, cfg: dict, loaded_mtime: float | None = None) -> float:
    """Write ``cfg`` atomically, keeping the old file as ``.bak``; returns the new mtime."""
    if loaded_mtime is not None and path.exists() and path.stat().st_mtime != loaded_mtime:
        raise ConfigChanged(f"{path.name} was changed on disk after it was loaded.")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(tmp, path)
    return path.stat().st_mtime


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_number(key: str, value, errors: dict[str, str]) -> None:
    low, high = RANGES[key]
    if key in INTEGER_KEYS:
        if not isinstance(value, int) or isinstance(value, bool):
            errors[key] = "Must be a whole number."
            return
    elif not _is_number(value):
        errors[key] = "Must be a number."
        return
    if not low <= value <= high:
        errors[key] = f"Must be between {low:g} and {high:g}."


def _hotkey_keys(text) -> frozenset | None:
    """The parsed keys of a hotkey string, or None if it does not parse."""
    if not isinstance(text, str):
        return None
    try:
        return frozenset(HotKey.parse(text))
    except ValueError:
        return None


def _validate_domain(name: str, domain, errors: dict[str, str]) -> frozenset | None:
    """Check one Domain; returns its parsed hotkey for the duplicate check."""
    path = f"domains.{name}"
    if not SIGN_NAME.match(name):
        errors[path] = "Name may only use letters, numbers and underscores."
    if not isinstance(domain, dict):
        errors[path] = "Must be an object."
        return None
    for key in ("title", "video"):
        if key in domain and not isinstance(domain[key], str):
            errors[f"{path}.{key}"] = "Must be text."
    keywords = domain.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        errors[f"{path}.keywords"] = "Must be a list of words."
    start = domain.get("loop_start_sec")
    if not _is_number(start) or start < 0:
        errors[f"{path}.loop_start_sec"] = "Must be a number of seconds, 0 or more."
        start = None
    end = domain.get("loop_end_sec")
    if end is not None and (not _is_number(end) or (start is not None and end <= start)):
        errors[f"{path}.loop_end_sec"] = "Must be empty or later than the loop start."
    keys = _hotkey_keys(domain.get("hotkey"))
    if keys is None:
        errors[f"{path}.hotkey"] = "Not a valid hotkey, e.g. <ctrl>+<alt>+d."
    return keys


def _validate_action(name: str, action, domain_names, errors: dict[str, str]) -> None:
    path = f"actions.{name}"
    if not SIGN_NAME.match(name):
        errors[path] = "Name may only use letters, numbers and underscores."
    elif name in domain_names:
        errors[path] = "This sign already opens a Domain; use a different name."
    else:
        kinds = [k for k in ACTION_TYPES if k in action] if isinstance(action, dict) else []
        if len(kinds) != 1 or not isinstance(action[kinds[0]], str) or not action[kinds[0]].strip():
            errors[path] = f"Needs exactly one of {', '.join(ACTION_TYPES)} with a text value."


def validate(cfg: dict) -> dict[str, str]:
    """Problems in ``cfg`` as field path -> message; empty when it is valid."""
    errors: dict[str, str] = {}
    for key in REQUIRED_KEYS:
        if key not in cfg:
            errors[key] = "Required."
    for key in RANGES:
        if key in cfg:
            _validate_number(key, cfg[key], errors)
    if "quality" in cfg and cfg["quality"] not in QUALITIES:
        errors["quality"] = f"Must be one of {', '.join(QUALITIES)}."
    for key in ("show_preview", "mirror_preview"):
        if key in cfg and not isinstance(cfg[key], bool):
            errors[key] = "Must be on or off."

    domains = cfg.get("domains")
    if not isinstance(domains, dict):
        errors["domains"] = "Required."
        domains = {}
    hotkeys: dict[str, frozenset] = {}
    for name, domain in domains.items():
        keys = _validate_domain(name, domain, errors)
        if keys is not None:
            hotkeys[name] = keys
    for name, keys in hotkeys.items():
        if any(other != name and other_keys == keys for other, other_keys in hotkeys.items()):
            errors[f"domains.{name}.hotkey"] = "Another Domain uses the same hotkey."

    actions = cfg.get("actions", {})
    if not isinstance(actions, dict):
        errors["actions"] = "Must be an object."
        actions = {}
    for name, action in actions.items():
        _validate_action(name, action, domains, errors)
    return errors


def known_signs(cfg: dict, samples_dir: Path) -> list[str]:
    """Every sign name that can be picked: built-in, Domain, or taught from samples/."""
    taught = ([d.name for d in samples_dir.iterdir() if d.is_dir()]
              if samples_dir.is_dir() else [])
    names = set(GESTURES) | set(cfg.get("domains", {})) | set(taught)
    return sorted(names - {NONE_LABEL})


def _move_back(moved_to: Path, moved_from: Path) -> None:
    """Undo a folder move after a failed save; says where the recordings are if it cannot."""
    try:
        os.replace(moved_to, moved_from)
    except OSError as exc:
        raise RenameError(f"The config was not changed, but the recordings could not be moved "
                          f"back from {moved_to} to {moved_from}: {exc}") from exc


def rename_sign(cfg: dict, kind: str, old: str, new: str, config_path: Path,
                samples_dir: Path, loaded_mtime: float | None = None) -> tuple[dict, float]:
    """Rename a Domain or action together with its ``samples/<name>`` recordings.

    ``kind`` is "domain" or "action". All or nothing: on any refusal or failure the
    disk and ``cfg`` are left as they were, and ``RenameError`` is raised. Returns
    the saved config (the renamed key keeps its position) and its new mtime.
    """
    section = {"domain": "domains", "action": "actions"}.get(kind)
    if section is None:
        raise RenameError(f"Unknown kind of sign: {kind}.")
    if old in GESTURES:
        raise RenameError(f"{old} is a built-in sign and cannot be renamed.")
    if old not in cfg.get(section, {}):
        raise RenameError(f"There is no {kind} called {old}.")
    if not SIGN_NAME.match(new):
        raise RenameError("Name may only use letters, numbers and underscores.")
    source, target = samples_dir / old, samples_dir / new
    if (new in GESTURES or new == NONE_LABEL or new in cfg.get("domains", {})
            or new in cfg.get("actions", {}) or target.exists()):
        raise RenameError(f"The name {new} is already used; pick a different one.")

    renamed = copy.deepcopy(cfg)
    renamed[section] = {(new if key == old else key): value
                        for key, value in renamed[section].items()}
    move_folder = source.is_dir()
    if move_folder:
        try:
            os.replace(source, target)
        except PermissionError as exc:
            raise RenameError("Could not move the recordings folder; it is in use. Close "
                              "teach.bat/record.bat and try again.") from exc
        except OSError as exc:
            raise RenameError(f"Could not move the recordings folder: {exc}") from exc
    try:
        mtime = save(config_path, renamed, loaded_mtime)
    except ConfigChanged as exc:
        if move_folder:
            _move_back(target, source)
        raise RenameError(f"{config_path.name} was changed outside this window; "
                          "reload it and try again.") from exc
    except OSError as exc:
        if move_folder:
            _move_back(target, source)
        raise RenameError(f"Could not save {config_path.name}: {exc}") from exc
    return renamed, mtime
