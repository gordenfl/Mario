# Mario Tools

与 `client/` 平级的开发工具目录。

## 环境

```bash
cd tools
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install assimp   # FBX/OBJ → GLB 转换（仅需安装一次）
```

## 1. 3D 模型 / 动作查看器

预览 `client/Assets/Art/Characters/3dmodel/` 下的角色模型与 FBX 动作。

```bash
source .venv/bin/activate
python model_viewer.py
# 或: python -m model_viewer
```

- **模型列表**：`client/Assets/Art/Characters/3dmodel/` 下每个子文件夹为一个模型（如 `panda_warrior`）
- 点击模型名：加载该目录下的默认网格（优先 `模型名.obj`）并显示
- **动作列表**：该模型 `Animations/` 下的 FBX，点击可切换播放
- **鼠标**：拖拽旋转视角，滚轮缩放
- 若动作文件内有多条动画轨道，可在「轨道」下拉框中切换

资源根目录：

`client/Assets/Art/Characters/3dmodel/`

每个模型一个子目录，例如：

```
3dmodel/panda_warrior/
  panda_warrior.obj      # 默认显示的网格
  Animations/Idle.fbx    # 动作
  Textures/              # 贴图（可选）
```
