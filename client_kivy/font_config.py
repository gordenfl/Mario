"""Register Chinese-capable UI font (same as pygame client `client/fonts/Regular.ttf`)."""

from __future__ import annotations

from pathlib import Path

# Resolved once at import time
_REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_FONT_TTF = _REPO_ROOT / "client" / "fonts" / "Regular.ttf"

# Registered name for Kivy LabelBase
UI_FONT_NAME = "MarioUI"

_registered: bool = False
_active_font_name: str | None = None


def get_ui_font_name() -> str | None:
    """Use on widgets as font_name=get_ui_font_name() after register_ui_font() was called."""
    return _active_font_name


def register_ui_font() -> str | None:
    """
    Register `Regular.ttf` with Kivy. Call once before building widgets.
    Returns the font name to pass as font_name=..., or None if registration skipped.
    """
    global _registered, _active_font_name
    if _registered:
        return _active_font_name
    if not CLIENT_FONT_TTF.is_file():
        _active_font_name = None
        return None
    try:
        from kivy.core.text import LabelBase

        LabelBase.register(name=UI_FONT_NAME, fn_regular=str(CLIENT_FONT_TTF))
        _registered = True
        _active_font_name = UI_FONT_NAME
        return _active_font_name
    except Exception:
        _active_font_name = None
        return None


def text_font_kwargs() -> dict:
    """Pass as Label/Button/TextInput: `**text_font_kwargs()`."""
    n = get_ui_font_name()
    return {"font_name": n} if n else {}
