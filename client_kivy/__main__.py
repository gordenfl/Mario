from __future__ import annotations

from ._graphics_config import apply_kivy_graphics_config

apply_kivy_graphics_config()

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

    def on_pause(self):
        """Stop the game loop while backgrounded (saves battery on iOS/Android)."""
        root = self.root
        if root and hasattr(root, "get_screen"):
            game = root.get_screen("game")
            gv = getattr(game, "_game_view", None)
            if gv is not None:
                gv.stop_tick()
        return True

    def on_resume(self):
        root = self.root
        if root and hasattr(root, "get_screen") and getattr(root, "current", None) == "game":
            game = root.get_screen("game")
            gv = getattr(game, "_game_view", None)
            if gv is not None and not getattr(gv, "_match_end_fired", False):
                gv.start_tick()


if __name__ == "__main__":
    MarioFightKivyApp().run()

