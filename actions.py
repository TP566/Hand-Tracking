"""PC actions triggered by hand signs (the "actions" block in config.json).

Each entry maps a sign name to exactly one action:
  {"keys": "ctrl+shift+f9"}      press a keyboard shortcut
  {"type": "gg"}                 type text
  {"open": "https://..."}        open an app, file or website
"""

import os

import pyautogui

ACTION_TYPES = ("keys", "type", "open")


def validate(actions_cfg: dict, domain_names) -> dict[str, dict]:
    """Usable actions; prints a warning for each bad entry.

    A sign can open a Domain or run an action, not both: that would be ambiguous,
    so it stops the app with a clear message.
    """
    clash = sorted(set(actions_cfg) & set(domain_names))
    if clash:
        raise SystemExit(f"These signs are used for both a Domain and an action in config.json: "
                         f"{', '.join(clash)}. Use a different sign name for one of them.")
    valid = {}
    for name, action in actions_cfg.items():
        kinds = [k for k in ACTION_TYPES if k in action] if isinstance(action, dict) else []
        if len(kinds) != 1 or not isinstance(action[kinds[0]], str) or not action[kinds[0]].strip():
            print(f"[{name}] Ignoring action: it needs exactly one of {', '.join(ACTION_TYPES)} "
                  f"with a text value, e.g. {{\"keys\": \"ctrl+shift+f9\"}}.")
            continue
        valid[name] = action
    return valid


def describe(action: dict) -> str:
    kind = next(k for k in ACTION_TYPES if k in action)
    return {"keys": "press", "type": "type", "open": "open"}[kind] + " " + action[kind]


def run(action: dict) -> None:
    if "keys" in action:
        pyautogui.hotkey(*[k.strip().lower() for k in action["keys"].split("+")])
    elif "type" in action:
        pyautogui.write(action["type"])
    else:
        os.startfile(action["open"])


class Actions:
    def __init__(self, actions: dict[str, dict], runner=run):
        self.actions = actions
        self.runner = runner

    def __contains__(self, name: str) -> bool:
        return name in self.actions

    def __iter__(self):
        return iter(self.actions)

    def run(self, name: str) -> None:
        """Run the action for ``name``; a failure is reported, never raised."""
        action = self.actions[name]
        try:
            self.runner(action)
            print(f"[{name}] {describe(action)}")
        except Exception as e:
            print(f"[{name}] Action failed ({describe(action)}): {e}")
