from __future__ import annotations

from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent

# 资源根目录：其下每个子文件夹为一个角色模型（如 panda_warrior）
MODEL_ROOT = REPO_ROOT / "client/Assets/Art/Characters/3dmodel"

CACHE_DIR = TOOLS_DIR / ".cache" / "model_viewer"
