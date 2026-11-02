"""System tray icon with Settings and Quit entries.

The callbacks run on pystray's own thread, so the caller must pass thread-safe ones.
"""

from typing import Callable

import pystray
from PIL import Image, ImageDraw

PURPLE = (124, 58, 237, 255)
WHITE = (255, 255, 255, 255)


def make_icon_image(size: int = 64) -> Image.Image:
    """A purple disc with a white ring."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, size - 1, size - 1), fill=PURPLE)
    inset = size * 0.22
    draw.ellipse(
        (inset, inset, size - 1 - inset, size - 1 - inset),
        outline=WHITE,
        width=max(2, size // 12),
    )
    return image


def build_menu(
    on_settings: Callable[[], None], on_quit: Callable[[], None]
) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("Settings", lambda icon, item: on_settings()),
        pystray.MenuItem("Quit", lambda icon, item: on_quit()),
    )


def start_tray(
    on_settings: Callable[[], None], on_quit: Callable[[], None]
) -> pystray.Icon:
    """Show the tray icon on a background thread; the caller calls ``.stop()``."""
    icon = pystray.Icon(
        "hand_tracking",
        make_icon_image(),
        "Domain Expansion",
        build_menu(on_settings, on_quit),
    )
    icon.run_detached()
    return icon
