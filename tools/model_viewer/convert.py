from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


TEXTURE_GLOBS = (
    "*.JPEG",
    "*.jpeg",
    "*.JPG",
    "*.jpg",
    "*.PNG",
    "*.png",
)


def _assimp_bin() -> str:
    exe = shutil.which("assimp")
    if exe:
        return exe
    for candidate in (
        "/opt/homebrew/bin/assimp",
        "/usr/local/bin/assimp",
    ):
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(
        "未找到 assimp 命令行工具。请安装: brew install assimp"
    )


def _texture_source_dirs(source: Path, extra_dirs: list[Path] | None = None) -> list[Path]:
    dirs: list[Path] = []
    for folder in [source.parent.resolve(), *(extra_dirs or [])]:
        if folder.is_dir() and folder not in dirs:
            dirs.append(folder)
    return dirs


def sync_textures(
    source: Path, cache_dir: Path, extra_texture_dirs: list[Path] | None = None
) -> None:
    """把模型目录里的贴图复制到 GLB 缓存目录（assimp 常生成外部贴图引用）。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for folder in _texture_source_dirs(source, extra_texture_dirs):
        for pattern in TEXTURE_GLOBS:
            for tex in folder.glob(pattern):
                dest = cache_dir / tex.name
                if not dest.exists() or tex.stat().st_mtime > dest.stat().st_mtime:
                    shutil.copy2(tex, dest)


def _glb_needs_rebuild(
    source: Path,
    out: Path,
    cache_dir: Path,
    extra_texture_dirs: list[Path] | None = None,
) -> bool:
    if not out.is_file():
        return True
    if out.stat().st_mtime < source.stat().st_mtime:
        return True
    # 旧缓存 GLB 可能引用贴图但贴图未复制
    sync_textures(source, cache_dir, extra_texture_dirs)
    try:
        from pygltflib import GLTF2

        gltf = GLTF2().load(str(out))
        if not gltf.images:
            return False
        for image in gltf.images:
            uri = getattr(image, "uri", None)
            if not uri or uri.startswith("data:"):
                continue
            if not (cache_dir / Path(uri).name).is_file():
                return True
    except Exception:
        pass
    return False


def ensure_glb(
    source: Path,
    cache_dir: Path,
    extra_texture_dirs: list[Path] | None = None,
) -> Path:
    """
    将 .fbx / .obj / .gltf 转为 .glb（缓存），供 pygfx 加载动画。
    已缓存且比源文件新则直接返回缓存路径。
    """
    source = source.resolve()
    suffix = source.suffix.lower()
    if suffix == ".glb":
        sync_textures(source, cache_dir, extra_texture_dirs)
        return source

    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_name = source.stem.replace(" ", "_")
    out = cache_dir / f"{safe_name}.glb"

    sync_textures(source, cache_dir, extra_texture_dirs)

    if not _glb_needs_rebuild(source, out, cache_dir, extra_texture_dirs):
        return out

    assimp = _assimp_bin()
    result = subprocess.run(
        [assimp, "export", str(source), str(out)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError(
            f"assimp 转换失败: {source.name}\n{result.stdout}\n{result.stderr}"
        )

    sync_textures(source, cache_dir, extra_texture_dirs)
    return out
