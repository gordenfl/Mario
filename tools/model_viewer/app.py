"""
3D 模型查看器：
  - 左侧列出 3dmodel/ 下各模型目录
  - 选中模型 → 加载并显示
  - 可选 Animations/ 下的动作播放
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pygfx as gfx
from imgui_bundle import imgui
from rendercanvas.auto import RenderCanvas, loop
from wgpu.utils.imgui import ImguiRenderer

from .convert import ensure_glb, sync_textures
from .discover import (
    ActionEntry,
    ModelEntry,
    discover_animations,
    discover_models,
    is_animation_asset,
    pick_default_asset,
    pick_mesh_asset,
)
from .fonts import setup_imgui_cjk_font
from .materials import apply_textured_materials
from .paths import CACHE_DIR, MODEL_ROOT

PANEL_W = 280
SPLIT_W = 1
# 相机在 -Z 侧沿 +Z 看向模型正面（与角色朝向相反则翻转此向量）
FRONT_VIEW_DIR = (0.0, 0.0, -1.0)
FRAME_MARGIN = 1.35


class ModelViewerApp:
    def __init__(self) -> None:
        self.models: List[ModelEntry] = discover_models()
        if not self.models:
            print(f"未找到模型目录: {MODEL_ROOT}", file=sys.stderr)
            sys.exit(1)

        self.model_index = 0
        for i, m in enumerate(self.models):
            if m.name == "panda_warrior":
                self.model_index = i
                break

        self.actions: List[ActionEntry] = []
        self.action_index = 0
        self.status = "就绪"

        self.model_obj: Optional[gfx.WorldObject] = None
        self.skeleton_helper: Optional[gfx.SkeletonHelper] = None
        self.mixer: Optional[gfx.AnimationMixer] = None
        self.clips: List = []
        self.clip_actions: List = []
        self.selected_clip = 0

        self._pending_model_index: Optional[int] = None
        self._pending_action_index: Optional[int] = None
        self._pending_asset: Optional[Path] = None
        self._loaded_source: Optional[Path] = None
        self._pending_reframe = 0
        self._pending_refresh_models = False

        self.canvas = RenderCanvas(
            size=(1400, 720),
            title="Player 3D 模型查看器",
            update_mode="ondemand",
            vsync=True,
        )
        self.renderer = gfx.WgpuRenderer(self.canvas)
        self.viewport = gfx.Viewport(self.renderer)
        self.viewport.rect = self._view_rect()
        vw, vh = self.viewport.logical_size
        aspect = vw / vh if vh > 0 else 16 / 9
        self.camera = gfx.PerspectiveCamera(45, aspect, depth_range=(0.1, 500))
        self.scene = gfx.Scene()
        self.scene.add(gfx.AmbientLight(), gfx.DirectionalLight())

        self.clock = gfx.Clock()
        self.gui = ImguiRenderer(self.renderer.device, self.canvas)
        setup_imgui_cjk_font(self.gui)
        self.gui.set_gui(self._draw_imgui)

        self.renderer.add_event_handler(self._on_resize, "resize")
        gfx.OrbitController(self.camera, register_events=self.viewport)
        self._pending_model_index = self.model_index

    @property
    def current_model(self) -> ModelEntry:
        return self.models[self.model_index]

    def _logical_size(self) -> tuple[int, int]:
        return self.renderer.logical_size

    def _view_rect(self) -> tuple[int, int, int, int]:
        w, h = self._logical_size()
        x = PANEL_W + SPLIT_W
        return (x, 0, max(1, w - x), max(1, h))

    def _sync_viewport_rect(self) -> None:
        self.viewport.rect = self._view_rect()
        vw, vh = self.viewport.logical_size
        if vh > 0 and getattr(self, "camera", None) is not None:
            self.camera.aspect = vw / vh

    def _on_resize(self, _event) -> None:
        self._sync_viewport_rect()
        if self.model_obj is not None:
            self._frame_model()

    def _framing_sphere(self) -> Tuple[float, float, float, float]:
        """合并静止与整段动画的 AABB，得到能包住动作的包围球。"""
        bbox = self.model_obj.get_world_bounding_box()
        lo = np.asarray(bbox[0], dtype=np.float64)
        hi = np.asarray(bbox[1], dtype=np.float64)

        if self.mixer and self.clip_actions and self.clips:
            clip = self.clips[self.selected_clip]
            action = self.clip_actions[self.selected_clip]
            saved_time = action.time
            sample_count = max(24, min(80, int(clip.duration * 12)))
            for t in np.linspace(0.0, clip.duration, sample_count):
                action.time = float(t)
                self.mixer.update(0.0)
                b = self.model_obj.get_world_bounding_box()
                lo = np.minimum(lo, b[0])
                hi = np.maximum(hi, b[1])
            action.time = saved_time
            self.mixer.update(0.0)

        center = (lo + hi) * 0.5
        half = (hi - lo) * 0.5
        radius = float(np.linalg.norm(half))
        return (
            float(center[0]),
            float(center[1]),
            float(center[2]),
            max(radius, 1e-3),
        )

    def _frame_model(self) -> None:
        """正面取景，按右侧视口宽高比把模型（含动作幅度）完整框进画面。"""
        if self.model_obj is None:
            return
        self._sync_viewport_rect()
        cx, cy, cz, radius = self._framing_sphere()
        self.camera.show_object(
            (cx, cy, cz, radius),
            view_dir=FRONT_VIEW_DIR,
            up=(0.0, 1.0, 0.0),
            scale=FRAME_MARGIN,
        )

    def _cache_dir(self, model: ModelEntry | None = None) -> Path:
        model = model or self.current_model
        return CACHE_DIR / model.cache_key

    def _refresh_model_list(self) -> None:
        prev_name = self.models[self.model_index].name if self.models else None
        self.models = discover_models()
        if not self.models:
            self.status = f"未找到模型目录: {MODEL_ROOT}"
            self.model_index = 0
            self.actions = []
            self._clear_scene()
            self._loaded_source = None
            return

        self.model_index = 0
        if prev_name is not None:
            for i, model in enumerate(self.models):
                if model.name == prev_name:
                    self.model_index = i
                    break

        model = self.current_model
        self.actions = discover_animations(model)
        self.status = f"已刷新 · {len(self.models)} 个模型 · {model.name}"

    def _select_model(self, index: int) -> None:
        self.model_index = max(0, min(index, len(self.models) - 1))
        model = self.current_model
        self.actions = discover_animations(model)
        self.action_index = -1
        self._loaded_source = None

        asset = pick_default_asset(model)
        if asset is None:
            self.status = f"{model.name}：目录内没有可加载的模型或动作"
            self._clear_scene()
            return

        self._queue_asset(asset, f"正在加载: {model.name} …")
        self._sync_action_highlight(asset)

    def _queue_asset(self, path: Path, status_msg: str) -> None:
        resolved = path.resolve()
        if self._loaded_source == resolved and self._pending_asset is None:
            return
        self._pending_asset = path
        self.status = status_msg

    def _sync_action_highlight(self, loaded: Path) -> None:
        resolved = loaded.resolve()
        self.action_index = -1
        for i, entry in enumerate(self.actions):
            if entry.source_path.resolve() == resolved:
                self.action_index = i
                return

    def _clear_scene(self) -> None:
        if self.model_obj is not None:
            self.scene.remove(self.model_obj)
            self.model_obj = None
        if self.skeleton_helper is not None:
            self.scene.remove(self.skeleton_helper)
            self.skeleton_helper = None
        self.mixer = None
        self.clips = []
        self.clip_actions = []

    def _load_asset(self, source: Path, label: str) -> None:
        self._clear_scene()
        model = self.current_model
        cache_dir = self._cache_dir(model)
        texture_dirs = model.texture_dirs()
        source = source.resolve()

        display_source = source
        material_source: Path | None = None
        if is_animation_asset(model, source):
            mesh_path = pick_mesh_asset(model)
            if mesh_path is not None:
                material_source = mesh_path.resolve()

        try:
            display_glb = ensure_glb(display_source, cache_dir, texture_dirs)
            material_glb = (
                ensure_glb(material_source, cache_dir, texture_dirs)
                if material_source is not None
                else None
            )
        except Exception as exc:
            self.status = f"加载失败: {exc}"
            print(self.status, file=sys.stderr)
            return

        try:
            gltf_display = gfx.load_gltf(display_glb, quiet=True)
            gltf_material = (
                gfx.load_gltf(material_glb, quiet=True)
                if material_glb is not None
                else None
            )
        except Exception as exc:
            self.status = f"显示失败: {exc}"
            print(self.status, file=sys.stderr)
            return

        if not gltf_display.scene.children:
            self.status = "模型为空"
            return

        self.model_obj = gltf_display.scene.children[0]
        if gltf_material is not None and gltf_material.scene.children:
            if not apply_textured_materials(
                self.model_obj, gltf_material.scene.children[0]
            ):
                print("警告: 未能为动作模型套用贴图材质", file=sys.stderr)
        self.skeleton_helper = gfx.SkeletonHelper(self.model_obj)
        self.skeleton_helper.visible = False
        self.scene.add(self.skeleton_helper, self.model_obj)

        self.mixer = gfx.AnimationMixer()
        self.clips = list(gltf_display.animations or [])
        self.clip_actions = [self.mixer.clip_action(c) for c in self.clips]
        self.selected_clip = 0
        if self.clip_actions:
            self.clip_actions[0].play()
            self.status = f"{model.name} · {label}"
        else:
            self.status = f"{model.name} · {label}（静态）"
        self._loaded_source = source.resolve()
        self._frame_model()
        self._pending_reframe = 2 if self.clip_actions else 0

    def _draw_imgui(self) -> None:
        io = self.gui.backend.io
        win_h = io.display_size.y
        imgui.set_next_window_pos((0, 0), imgui.Cond_.always)
        imgui.set_next_window_size((PANEL_W, win_h), imgui.Cond_.always)
        expanded, _ = imgui.begin(
            "资源",
            None,
            flags=imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_scrollbar,
        )
        if not expanded:
            imgui.end()
            return

        imgui.text_wrapped(f"根目录:\n{MODEL_ROOT}")
        imgui.separator()

        imgui.align_text_to_frame_padding()
        imgui.text("模型列表")
        imgui.same_line()
        if imgui.small_button("刷新"):
            self._pending_refresh_models = True
        imgui.begin_child(
            "model_list",
            imgui.ImVec2(0, 140),
            child_flags=imgui.ChildFlags_.borders,
        )
        for i, model in enumerate(self.models):
            selected = i == self.model_index
            imgui.selectable(
                f"{'● ' if selected else '  '}{model.name}",
                selected,
            )
            if imgui.is_item_clicked() and i != self.model_index:
                self._pending_model_index = i
        imgui.end_child()

        imgui.separator()
        imgui.text_wrapped(self.status)

        model = self.current_model
        if self.actions:
            imgui.separator()
            imgui.text("动作 (Animations)")
            imgui.begin_child(
                "action_list",
                imgui.ImVec2(0, 160),
                child_flags=imgui.ChildFlags_.borders,
            )
            for i, entry in enumerate(self.actions):
                selected = i == self.action_index
                imgui.selectable(
                    f"{'● ' if selected else '  '}{entry.label}",
                    selected,
                )
                if imgui.is_item_clicked() and i != self.action_index:
                    self._pending_action_index = i
            imgui.end_child()
        else:
            imgui.separator()
            imgui.text_disabled("（无 Animations/ 动作）")

        if self.clip_actions:
            imgui.separator()
            names = [c.name or f"clip_{j}" for j, c in enumerate(self.clips)]
            changed, self.selected_clip = imgui.combo(
                "轨道",
                self.selected_clip,
                names,
                len(names),
            )
            if changed:
                for act in self.clip_actions:
                    act.stop()
                self.clip_actions[self.selected_clip].play()
                self._frame_model()
            act = self.clip_actions[self.selected_clip]
            if act.paused:
                if imgui.button("播放"):
                    act.paused = False
            else:
                if imgui.button("暂停"):
                    act.paused = True
            dur = self.clips[self.selected_clip].duration
            _, act.time = imgui.slider_float(
                "时间", act.time, 0.0, max(dur, 0.01)
            )

        show_sk = self.skeleton_helper.visible if self.skeleton_helper else False
        _, show_sk = imgui.checkbox("显示骨骼", show_sk)
        if self.skeleton_helper:
            self.skeleton_helper.visible = show_sk

        imgui.separator()
        imgui.text_wrapped("点选模型加载 · 点选动作切换动画\n右侧视口：拖拽旋转 · 滚轮缩放")

        pos = imgui.get_window_pos()
        draw = imgui.get_window_draw_list()
        x = pos.x + PANEL_W - 0.5
        draw.add_line(
            imgui.ImVec2(x, pos.y),
            imgui.ImVec2(x, pos.y + win_h),
            imgui.color_convert_float4_to_u32((0.45, 0.45, 0.5, 1.0)),
            SPLIT_W,
        )
        imgui.end()

    def _process_pending(self) -> None:
        if self._pending_refresh_models:
            self._pending_refresh_models = False
            self._refresh_model_list()
            return

        if self._pending_model_index is not None:
            idx = self._pending_model_index
            self._pending_model_index = None
            self._select_model(idx)
            return

        if self._pending_action_index is not None:
            idx = self._pending_action_index
            self._pending_action_index = None
            if 0 <= idx < len(self.actions):
                entry = self.actions[idx]
                self._queue_asset(
                    entry.source_path,
                    f"正在加载动作: {entry.label} …",
                )
            return

        if self._pending_asset is not None:
            path = self._pending_asset
            self._pending_asset = None
            label = path.stem
            for entry in self.actions:
                if entry.source_path.resolve() == path.resolve():
                    label = entry.label
                    break
            sync_textures(path, self._cache_dir(), self.current_model.texture_dirs())
            self._load_asset(path, label)
            self._sync_action_highlight(path)

    def _animate(self) -> None:
        self._process_pending()
        dt = self.clock.get_delta()
        if self.mixer:
            self.mixer.update(dt)
        if self._pending_reframe > 0:
            self._pending_reframe -= 1
            if self._pending_reframe == 0:
                self._frame_model()
        self._sync_viewport_rect()
        self.viewport.render(self.scene, self.camera, flush=True)
        self.gui.render()
        self.canvas.request_draw()

    def run(self) -> None:
        self.renderer.request_draw(self._animate)
        loop.run()


def main() -> None:
    if not MODEL_ROOT.is_dir():
        print(f"模型根目录不存在: {MODEL_ROOT}", file=sys.stderr)
        sys.exit(1)
    ModelViewerApp().run()
