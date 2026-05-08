from __future__ import annotations

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout

from .view import GameView


class MarioFightKivyApp(App):
    def build(self):
        # Prefer landscape; iOS orientation will be set in Xcode/plist later.
        try:
            # On desktop, allow resizing. The game renders to a fixed virtual
            # framebuffer (852x480) and auto-scales with letterboxing.
            Window.size = (1024, 576)
            Window.resizable = True
        except Exception:
            pass

        root = BoxLayout()
        root.add_widget(GameView())
        return root


if __name__ == "__main__":
    MarioFightKivyApp().run()

