from tray import build_menu, make_icon_image


def test_icon_image_size():
    assert make_icon_image(64).size == (64, 64)


def test_menu_items_call_handlers():
    calls = []
    menu = build_menu(lambda: calls.append("s"), lambda: calls.append("q"))
    items = {i.text: i for i in menu.items}
    assert set(items) == {"Settings", "Quit"}
    items["Settings"](None)
    items["Quit"](None)
    assert calls == ["s", "q"]
