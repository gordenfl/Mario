from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from kivy.graphics.texture import Texture


SPRITE_JSON_PATHS = [
    "sprites/Mario.json",
    "sprites/Goomba.json",
    "sprites/Koopa.json",
    "sprites/Animations.json",
    "sprites/BackgroundSprites.json",
    "sprites/ItemAnimations.json",
    "sprites/RedMushroom.json",
]


def _apply_colorkey(crop_rgba: Image.Image, colorkey: Any) -> Image.Image:
    img = crop_rgba.convert("RGBA")
    if colorkey is None:
        return img
    if colorkey == -1:
        r0, g0, b0 = img.getpixel((0, 0))[:3]
    elif isinstance(colorkey, (list, tuple)) and len(colorkey) == 3:
        r0, g0, b0 = colorkey[0], colorkey[1], colorkey[2]
    else:
        return img

    pdata = img.load()
    w, h = img.size
    for yy in range(h):
        for xx in range(w):
            pr, pg, pb = pdata[xx, yy][:3]
            if pr == r0 and pg == g0 and pb == b0:
                pdata[xx, yy] = (pr, pg, pb, 0)
    return img


def pil_to_texture(im: Image.Image) -> Texture:
    im_rgba = im.convert("RGBA")
    w, h = im_rgba.size
    tex = Texture.create(size=(w, h))
    tex.blit_buffer(im_rgba.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    tex.flip_vertical()
    return tex


def load_sheet_image(abs_path: Path) -> Image.Image:
    img = Image.open(abs_path)
    try:
        if getattr(img, "is_animated", False):
            img.seek(0)
    except (EOFError, OSError):
        pass
    return img.convert("RGBA")


def pil_crop_scale(
    sheet: Image.Image,
    px: int,
    py: int,
    src_w: int,
    src_h: int,
    scale: int,
    colorkey: Any,
) -> Tuple[Texture, Tuple[int, int]]:
    crop = sheet.crop((px, py, px + src_w, py + src_h)).copy()
    crop = _apply_colorkey(crop, colorkey)
    tw = int(src_w * scale)
    th = int(src_h * scale)
    crop = crop.resize((tw, th), Image.NEAREST)
    return pil_to_texture(crop), (tw, th)


def extract_tile_sheet(
    sheet: Image.Image,
    tx: float,
    ty: float,
    scalefactor: int,
    colorkey: Any,
    x_tile_px: int = 16,
    y_tile_px: int = 16,
) -> Tuple[Texture, Tuple[int, int]]:
    """Spritesheet coords in tiles (pygame Spritesheet without ignore_tile_size)."""
    sx = int(tx * x_tile_px)
    sy = int(ty * y_tile_px)
    return pil_crop_scale(
        sheet, sx, sy, x_tile_px, y_tile_px, scalefactor, colorkey
    )


@dataclass
class AnimatedSpriteTextures:
    frames: List[Texture]
    widths: List[int]
    heights: List[int]
    delta_time: int = 10
    _t_frames: float = field(default=0.0, repr=False)

    def texture_at_time(self, dt_seconds: float) -> Tuple[Texture, Tuple[int, int]]:
        if not self.frames:
            tex = Texture.create(size=(2, 2))
            tex.min_filter = tex.mag_filter = "nearest"
            return tex, (2, 2)
        self._t_frames += dt_seconds
        dur = max(1, self.delta_time) / 60.0
        idx = int(self._t_frames / dur) % len(self.frames)
        return self.frames[idx], (self.widths[idx], self.heights[idx])


class SpriteRepository:
    """
    Mirrors pygame client JSON sprite loading into static Kivy textures.
    Texture filter: nearest-neighbor for pixel art.
    """

    def __init__(self, client_root: Path) -> None:
        self.client_root = client_root.resolve()
        self.static: Dict[str, Tuple[Texture, Tuple[int, int]]] = {}
        self.animated: Dict[str, AnimatedSpriteTextures] = {}
        self._sheet_images: Dict[str, Image.Image] = {}
        self._flip_cache: Dict[str, Tuple[Texture, Tuple[int, int]]] = {}

    def load_all(self) -> None:
        for rel in SPRITE_JSON_PATHS:
            json_path = self.client_root / rel
            if not json_path.is_file():
                continue
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self._consume_json(data)

    def _resolve_sheet_path(self, rel_url: str) -> Path:
        return (self.client_root / rel_url.lstrip("./")).resolve()

    def _sheet(self, rel_url: str) -> Image.Image:
        p = self._resolve_sheet_path(rel_url)
        key = str(p)
        cached = self._sheet_images.get(key)
        if cached is not None:
            return cached
        img = load_sheet_image(p)
        self._sheet_images[key] = img
        return img

    def _nearest_filter(self, tex: Texture):
        tex.mag_filter = "nearest"
        tex.min_filter = "nearest"

    def get_static(self, name: str, *, flip_x: bool = False) -> Optional[Tuple[Texture, Tuple[int, int]]]:
        base = self.static.get(name)
        if not base:
            return None
        if not flip_x:
            return base
        cached = self._flip_cache.get(name)
        if cached:
            return cached
        tex, (w, h) = base
        # Create a flipped copy from texture pixel buffer.
        try:
            buf = tex.pixels  # RGBA bytes
            im = Image.frombytes("RGBA", (w, h), buf)
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
            ftex = pil_to_texture(im)
            self._nearest_filter(ftex)
            self._flip_cache[name] = (ftex, (w, h))
            return self._flip_cache[name]
        except Exception:
            return base

    def _consume_json(self, data: dict) -> None:
        sheet_url = data["spriteSheetURL"]
        sheet = self._sheet(sheet_url)
        stype = data["type"]
        base_size = data.get("size", [16, 16])

        if stype == "background":
            for sp in data["sprites"]:
                name = sp["name"]
                ck = None
                if "colorKey" in sp:
                    ck = sp["colorKey"]
                tex, size = extract_tile_sheet(
                    sheet,
                    float(sp["x"]),
                    float(sp["y"]),
                    int(sp["scalefactor"]),
                    ck,
                )
                self._nearest_filter(tex)
                self.static[name] = (tex, size)
            return

        if stype == "animation":
            for sp in data["sprites"]:
                name = sp["name"]
                frames: List[Texture] = []
                widths: List[int] = []
                heights: List[int] = []
                ck = sp.get("colorKey", None)
                for im in sp["images"]:
                    tex, sz = extract_tile_sheet(
                        sheet,
                        float(im["x"]),
                        float(im["y"]),
                        int(im["scale"]),
                        ck,
                    )
                    self._nearest_filter(tex)
                    frames.append(tex)
                    widths.append(sz[0])
                    heights.append(sz[1])
                self.animated[name] = AnimatedSpriteTextures(
                    frames=frames,
                    widths=widths,
                    heights=heights,
                    delta_time=int(sp.get("deltaTime", 10)),
                )
            return

        if stype in ("character", "item"):
            for sp in data["sprites"]:
                name = sp["name"]
                ck = sp.get("colorKey", None)
                if "xsize" in sp and "ysize" in sp:
                    xsize = int(sp["xsize"])
                    ysize = int(sp["ysize"])
                else:
                    xsize, ysize = int(base_size[0]), int(base_size[1])
                px = int(sp["x"])
                py = int(sp["y"])
                scale = int(sp["scalefactor"])
                tex, size = pil_crop_scale(sheet, px, py, xsize, ysize, scale, ck)
                self._nearest_filter(tex)
                self.static[name] = (tex, size)
            return


def animated_frame_for(
    ani: AnimatedSpriteTextures, frame_index: int
) -> Tuple[Texture, Tuple[int, int]]:
    frame_index = frame_index % len(ani.frames)
    return ani.frames[frame_index], (ani.widths[frame_index], ani.heights[frame_index])


def mario_pick_frame_name(
    on_ground: bool, vel_x_mag: float, anim_tick: int, big: bool = True
) -> str:
    """
    Select static texture name (idle / run frames / jump) — simple state machine like pygame GoTrait + Animation.
    """
    prefix = "mario_big_" if big else "mario_"
    if not on_ground:
        return f"{prefix}jump"
    running = vel_x_mag > 0.15
    if not running:
        return f"{prefix}idle"
    run_names = (
        ["mario_big_run1", "mario_big_run2", "mario_big_run3"]
        if big
        else ["mario_run1", "mario_run2", "mario_run3"]
    )
    stride = max(1, int(7 * (60 / max(45.0, 60))))
    idx = (anim_tick // stride) % 3
    return run_names[idx]
