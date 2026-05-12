"""Server-side configuration derived from level data."""

from __future__ import annotations

import json
import logging
import os


def _load_level_length(default_tiles: int = 60) -> int:
    level_path = os.path.join(os.path.dirname(__file__), "..", "client", "levels", "Level1-1.json")
    try:
        with open(level_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            length = int(data.get("length", default_tiles))
            if length > 0:
                return length
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logging.warning("Failed to load level length from %s: %s", level_path, exc)
    return default_tiles


LEVEL_TILE_LENGTH = _load_level_length()
LEVEL_WIDTH_PIXELS = LEVEL_TILE_LENGTH * 32
