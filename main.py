"""
iOS 打包入口：kivy-ios 的 `toolchain create` 要求应用目录根下有 `main.py`。

本机调试桌面端仍推荐使用：python -m client_kivy
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client_kivy.__main__ import MarioFightKivyApp

if __name__ == "__main__":
    MarioFightKivyApp().run()
