from __future__ import annotations

from kivy.app import App
from kivy.core.window import Window

from .font_config import register_ui_font


class MarioFightKivyApp(App):
    def build(self):
        # Chinese UI: register client/fonts/Regular.ttf before any widgets.
        register_ui_font()

        from .screens import build_screen_manager

        # Prefer landscape; iOS orientation will be set in Xcode/plist later.
        try:
            # On desktop, allow resizing. The game renders to a fixed virtual
            # framebuffer (852x480) and auto-scales with letterboxing.
            Window.size = (1024, 576)
            Window.resizable = True
        except Exception:
            pass

        return build_screen_manager()


if __name__ == "__main__":
    MarioFightKivyApp().run()

