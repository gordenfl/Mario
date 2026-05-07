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

### Notes

- This is intentionally a minimal loop first (rendering uses simple shapes).
- Next steps are to wire in the existing network lobby/game protocol and replace placeholder rendering with sprite textures.

