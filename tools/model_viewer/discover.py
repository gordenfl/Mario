from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .paths import MODEL_ROOT


@dataclass(frozen=True)
class ModelEntry:
    """3dmodel 下的一个模型目录（如 panda_warrior）。"""

    name: str
    root: Path

    @property
    def cache_key(self) -> str:
        return self.name.replace(" ", "_")

    def animation_dir(self) -> Optional[Path]:
        anim = self.root / "Animations"
        return anim if anim.is_dir() else None

    def texture_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        for folder in (self.root, self.root / "Textures"):
            if folder.is_dir() and folder not in dirs:
                dirs.append(folder)
        anim = self.animation_dir()
        if anim is not None and anim not in dirs:
            dirs.append(anim)
        return dirs


@dataclass(frozen=True)
class ActionEntry:
    """模型目录下的一个动作（FBX）。"""

    label: str
    source_path: Path


def discover_models() -> List[ModelEntry]:
    """列出 MODEL_ROOT 下的一级子目录（每个即一个模型）。"""
    models: List[ModelEntry] = []
    if not MODEL_ROOT.is_dir():
        return models

    for child in sorted(MODEL_ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        models.append(ModelEntry(name=child.name, root=child.resolve()))

    return models


def discover_animations(model: ModelEntry) -> List[ActionEntry]:
    """模型 Animations/ 目录下的 FBX 动作。"""
    entries: List[ActionEntry] = []
    anim_dir = model.animation_dir()
    if anim_dir is None:
        return entries
    for path in sorted(anim_dir.glob("*.fbx"), key=lambda p: p.stem.lower()):
        entries.append(ActionEntry(label=path.stem, source_path=path))
    for path in sorted(anim_dir.glob("*.glb"), key=lambda p: p.stem.lower()):
        entries.append(ActionEntry(label=path.stem, source_path=path))
    return entries


def _mesh_candidates(model: ModelEntry) -> List[Path]:
    meshes: List[Path] = []
    preferred = model.root / f"{model.name}.obj"
    if preferred.is_file():
        meshes.append(preferred)
    for pattern in ("*.obj", "*.glb", "*.gltf"):
        for path in sorted(model.root.glob(pattern)):
            if path not in meshes:
                meshes.append(path)
    meshes.sort(key=lambda p: (p.name != f"{model.name}.obj", p.stat().st_size))
    return meshes


def pick_mesh_asset(model: ModelEntry) -> Optional[Path]:
    """带贴图的静态网格（.obj 等），用于显示角色外观。"""
    meshes = _mesh_candidates(model)
    return meshes[0] if meshes else None


def is_animation_asset(model: ModelEntry, source: Path) -> bool:
    anim_dir = model.animation_dir()
    if anim_dir is None:
        return False
    try:
        return source.resolve().parent == anim_dir.resolve()
    except OSError:
        return False


def pick_default_asset(model: ModelEntry) -> Optional[Path]:
    """
    选中模型时默认加载的资源：
    1. 与目录同名的 .obj（如 panda_warrior/panda_warrior.obj）
    2. 目录下其它网格
    3. Animations/Idle.fbx
    4. 第一个动作 FBX
    """
    meshes = _mesh_candidates(model)
    if meshes:
        return meshes[0]

    anims = discover_animations(model)
    for entry in anims:
        if entry.label.lower() == "idle":
            return entry.source_path
    if anims:
        return anims[0].source_path

    return None
