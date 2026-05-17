"""ImGui 中文字体（macOS 系统字体 + hello_imgui 加载）。"""
from __future__ import annotations

from pathlib import Path

from imgui_bundle import hello_imgui, imgui
from wgpu.utils.imgui import ImguiRenderer

def _find_cjk_font_path() -> Path | None:
    candidates = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def setup_imgui_cjk_font(gui: ImguiRenderer, size_px: float = 9.0) -> None:
    imgui.set_current_context(gui.imgui_context)
    io = imgui.get_io()
    io.fonts.clear()

    font_path = _find_cjk_font_path()
    if font_path is not None:
        hello_imgui.load_font_ttf(str(font_path), size_px)
        return

    io.fonts.add_font_default()
    io.font_global_scale = 0.5
