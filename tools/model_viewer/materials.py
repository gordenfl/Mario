"""把带贴图的网格材质套到骨骼模型上。"""
from __future__ import annotations

import pygfx as gfx


def _materials_with_map(root: gfx.WorldObject) -> list:
    mats: list = []
    for child in root.iter():
        mat = getattr(child, "material", None)
        if mat is not None and getattr(mat, "map", None) is not None:
            mats.append(mat)
    return mats


def _meshes_with_material(root: gfx.WorldObject) -> list:
    return [
        child
        for child in root.iter()
        if getattr(child, "material", None) is not None
    ]


def apply_textured_materials(
    target_root: gfx.WorldObject, source_root: gfx.WorldObject
) -> bool:
    """
    将 source 中带 map 的材质赋给 target 的网格（用于动作 SkinnedMesh）。
    返回是否成功套用至少一个材质。
    """
    source_mats = _materials_with_map(source_root)
    if not source_mats:
        return False

    targets = _meshes_with_material(target_root)
    if not targets:
        return False

    for i, mesh in enumerate(targets):
        mesh.material = source_mats[min(i, len(source_mats) - 1)]
    return True
