"""
Kivy graphics config must apply before importing kivy.window / kivy.app (GL context creation).

Loaded when ``client_kivy.__main__`` is imported (including repo root ``main.py`` importing ``MarioFightKivyApp``).
"""

from __future__ import annotations

import os

# Global client cap (Kivy main loop). The game physics advances once per
# scheduled 1/60 tick, so the default must stay at 60 to avoid slow motion.
# Override with MARIO_MAX_FPS if needed.
DEFAULT_MAX_FPS = 60


def apply_kivy_graphics_config() -> None:
    """Cap redraw rate for the whole client; env MARIO_MAX_FPS overrides. Disable MSAA globally."""
    from kivy.config import Config
    from kivy.utils import platform as kivy_platform

    raw = os.environ.get("MARIO_MAX_FPS", "").strip()
    if raw.isdigit():
        cap = max(15, min(120, int(raw)))
    else:
        cap = DEFAULT_MAX_FPS
    # Physics uses a fixed 60 Hz accumulator; capping draw at 60 saves GPU/CPU on mobile.
    if kivy_platform in ("ios", "android") and not raw.isdigit():
        cap = DEFAULT_MAX_FPS
    Config.set("graphics", "maxfps", str(cap))

    try:
        Config.set("graphics", "multisamples", "0")
    except Exception:
        pass
