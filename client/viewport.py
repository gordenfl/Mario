"""
Shared virtual framebuffer sizing for pygame and Kivy clients.

Kivy expands horizontal world space on wide landscape screens (typical phones).
Pygame uses the same formula so the PC match view matches mobile.
"""

VIRTUAL_W = 852.0
VIRTUAL_H = 480.0
VIRTUAL_MIN_ASPECT = VIRTUAL_W / VIRTUAL_H

# Typical phone landscape (~19.5:9); used for default pygame window width.
PHONE_LANDSCAPE_ASPECT = 2.17


def default_window_size() -> tuple[int, int]:
    """Pygame window size that yields the same virtual width as a phone in landscape."""
    w = max(int(VIRTUAL_W), int(round(VIRTUAL_H * PHONE_LANDSCAPE_ASPECT)))
    return w, int(VIRTUAL_H)


def compute_virtual_framebuffer(window_w: float, window_h: float) -> tuple[float, float]:
    """
  Map physical window pixels to game virtual size (world / camera space).

  Matches `client_kivy.view.GameView._compute_view_transform`.
  """
    w = float(window_w)
    h = float(window_h)
    if w <= 1 or h <= 1:
        return VIRTUAL_W, VIRTUAL_H
    aspect = w / h
    if aspect >= VIRTUAL_MIN_ASPECT:
        scale = h / VIRTUAL_H
        virtual_w = max(VIRTUAL_W, w / scale)
        return virtual_w, VIRTUAL_H
    scale = w / VIRTUAL_W
    return VIRTUAL_W, h / scale
