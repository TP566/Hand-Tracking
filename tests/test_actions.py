import pytest

import actions


def test_each_action_type_runs_the_right_call(monkeypatch):
    calls = []
    monkeypatch.setattr(actions.pyautogui, "hotkey", lambda *keys: calls.append(("hotkey", keys)))
    monkeypatch.setattr(actions.pyautogui, "write", lambda text: calls.append(("write", text)))
    monkeypatch.setattr(actions.os, "startfile", lambda target: calls.append(("open", target)), raising=False)
    actions.run({"keys": "Ctrl + Shift+F9"})
    actions.run({"type": "gg"})
    actions.run({"open": "https://discord.com"})
    assert calls == [("hotkey", ("ctrl", "shift", "f9")), ("write", "gg"), ("open", "https://discord.com")]


def test_bad_entries_are_reported_and_skipped(capsys):
    valid = actions.validate({
        "mute": {"keys": "ctrl+shift+f9"},
        "nothing": {},
        "two": {"keys": "a", "type": "b"},
        "empty": {"type": "  "},
        "number": {"keys": 5},
        "text": "ctrl+m",
    }, domain_names=[])
    assert list(valid) == ["mute"]
    out = capsys.readouterr().out
    for name in ("nothing", "two", "empty", "number", "text"):
        assert f"[{name}]" in out


def test_sign_used_for_domain_and_action_is_rejected():
    with pytest.raises(SystemExit, match="unlimited_void"):
        actions.validate({"unlimited_void": {"keys": "a"}}, domain_names=["unlimited_void", "malevolent_shrine"])


def test_failing_action_is_reported_not_raised(capsys):
    def boom(action):
        raise OSError("no such app")

    acts = actions.Actions({"launch": {"open": "missing.exe"}}, runner=boom)
    assert "launch" in acts and list(acts) == ["launch"]
    acts.run("launch")
    assert "Action failed" in capsys.readouterr().out


def test_describe():
    assert actions.describe({"keys": "ctrl+shift+f9"}) == "press ctrl+shift+f9"
    assert actions.describe({"open": "x"}) == "open x"
