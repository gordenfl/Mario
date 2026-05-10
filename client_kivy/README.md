## client_kivy

Kivy-native client (iOS-friendly).

### Controls (touch)

- **Left half**: virtual joystick
  - Horizontal: move left/right
  - Up direction: jump
- **Right half**: tap/hold to fire

### Run locally (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r client_kivy/requirements.txt
python -m client_kivy
```

### Assets

Sprites and tiles are loaded from the existing **`client/`** bundle (same JSON + PNG/GIF sheets as pygame):
`client/sprites/*.json`, `client/img/tiles.png`, `client/img/characters.gif`, etc.

Fireballs remain **vector circles** like the pygame client (no separate fire texture in repo).

### iOS 打包（Xcode / IPA）

仓库根目录 **`main.py`** 供 kivy-ios 使用；完整步骤见 **`BuildIOSWITHPYTHON.md`**。

