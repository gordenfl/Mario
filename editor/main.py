import copy
import json
import os
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk


TILE_SIZE = 32
MIN_HEIGHT_TILES = 16
BACKGROUND_COLOR = "#89cff0"

OBJECT_CONFIG: Dict[str, Dict] = {
    "ground": {"label": "Ground", "kind": "single", "sprites": ["ground"]},
    "bricks": {"label": "Bricks", "kind": "single", "sprites": ["bricks"]},
    "sky": {"label": "Sky", "kind": "single", "sprites": ["sky"]},
    "bush": {"label": "Bush", "kind": "sequence", "sprites": ["bush_1", "bush_2", "bush_3"]},
    "cloud": {"label": "Cloud", "kind": "sequence", "sprites": ["cloud1_1", "cloud1_2", "cloud1_3"]},
    "pipe": {
        "label": "Pipe",
        "kind": "pipe",
        "top": ["pipeL", "pipeR"],
        "body": ["pipe2L", "pipe2R"],
        "default_height": 3,
    },
}

ENTITY_CONFIG: Dict[str, Dict] = {
    "CoinBox": {"label": "Coin Box", "sprite": "CoinBox"},
    "coinBrick": {"label": "Coin Brick", "sprite": "bricks"},
    "coin": {"label": "Coin", "sprite": "coin"},
    "Goomba": {"label": "Goomba", "sprite": "goomba-1"},
    "Koopa": {"label": "Koopa", "sprite": "koopa-1"},
    "RandomBox": {"label": "Random Box", "sprite": "CoinBox"},
    "RedMushroom": {"label": "Red Mushroom", "sprite": "mushroom"},
}


SPRITE_JSON_FILES = [
    "BackgroundSprites.json",
    "Animations.json",
    "ItemAnimations.json",
    "Goomba.json",
    "Koopa.json",
    "RedMushroom.json",
]


def resource_path(*parts: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


class SpriteLibrary:
    def __init__(self, client_dir: str):
        self.client_dir = client_dir
        self.photo_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.pil_sprites: Dict[str, Image.Image] = {}
        for file_name in SPRITE_JSON_FILES:
            path = resource_path("client", "sprites", file_name)
            if os.path.exists(path):
                self._load_sprite_file(path)

    @staticmethod
    def _apply_colorkey(image: Image.Image, key: Tuple[int, int, int]) -> Image.Image:
        image = image.convert("RGBA")
        new_data = []
        for px in image.getdata():
            if px[:3] == key:
                new_data.append((0, 0, 0, 0))
            else:
                new_data.append(px)
        image.putdata(new_data)
        return image

    def get_photo(self, name: str) -> Optional[ImageTk.PhotoImage]:
        if name in self.photo_cache:
            return self.photo_cache[name]
        pil = self.pil_sprites.get(name)
        if pil is None:
            return None
        photo = ImageTk.PhotoImage(pil)
        self.photo_cache[name] = photo
        return photo

    def build_preview(self, sprites: List[str]) -> Optional[ImageTk.PhotoImage]:
        images = [self.pil_sprites.get(name) for name in sprites if name in self.pil_sprites]
        if not images:
            return None
        height = max(img.height for img in images)
        width = sum(img.width for img in images)
        composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        cursor = 0
        for img in images:
            composite.paste(img, (cursor, 0), img)
            cursor += img.width
        photo = ImageTk.PhotoImage(composite)
        return photo

    def _load_sprite_file(self, path: str):
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        sheet_path = resource_path("client", data.get("spriteSheetURL", "").lstrip("./"))
        if not os.path.exists(sheet_path):
            return
        sheet = Image.open(sheet_path).convert("RGBA")
        default_size = data.get("size", [16, 16])
        stype = data.get("type", "")
        if stype == "animation":
            for sprite in data.get("sprites", []):
                name = sprite.get("name")
                if not name:
                    continue
                images = sprite.get("images", [])
                if not images:
                    continue
                first = images[0]
                scale = first.get("scale", sprite.get("scale", 1))
                image = self._extract_image(sheet, default_size, first.get("x", 0), first.get("y", 0), scale, sprite.get("colorKey"))
                self.pil_sprites[name] = image
        else:
            for sprite in data.get("sprites", []):
                name = sprite.get("name")
                if not name:
                    continue
                scale = sprite.get("scalefactor", sprite.get("scale", 1))
                xsize = sprite.get("xsize", default_size[0])
                ysize = sprite.get("ysize", default_size[1])
                image = self._extract_image(
                    sheet,
                    [xsize, ysize],
                    sprite.get("x", 0),
                    sprite.get("y", 0),
                    scale,
                    sprite.get("colorKey"),
                )
                self.pil_sprites[name] = image

    def _extract_image(self, sheet: Image.Image, size: List[int], tile_x: int, tile_y: int, scale: int, color_key):
        if scale is None:
            scale = 1
        if isinstance(color_key, list):
            color_key = tuple(color_key)
        if isinstance(color_key, int) and color_key < 0:
            color_key = None
        width, height = size if len(size) >= 2 else (16, 16)
        region = sheet.crop(
            (
                tile_x * width,
                tile_y * height,
                (tile_x + 1) * width,
                (tile_y + 1) * height,
            )
        )
        if color_key is not None:
            region = self._apply_colorkey(region, color_key)
        if scale != 1:
            region = region.resize((width * scale, height * scale), Image.NEAREST)
        return region


class LevelDocument:
    def __init__(self):
        self.path: Optional[str] = None
        self.data: Dict = {}
        self.new()

    def new(self):
        self.data = {
            "id": 0,
            "length": 60,
            "level": {
                "objects": {},
                "layers": {
                    "sky": {"x": [0, 60], "y": [0, 13]},
                    "ground": {"x": [0, 60], "y": [14, 16]},
                },
                "entities": {},
            },
        }
        self.path = None

    def load(self, path: str):
        with open(path, "r", encoding="utf-8") as fp:
            self.data = json.load(fp)
        self.path = path

    def save(self, path: Optional[str] = None):
        target = path or self.path
        if not target:
            raise ValueError("No file specified")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fp:
            json.dump(self.data, fp, indent=4)
        self.path = target

    def get_length(self) -> int:
        length = self.data.get("length")
        if isinstance(length, int) and length > 0:
            return length
        self.data["length"] = 60
        return 60

    def get_objects(self) -> Dict[str, List[List[int]]]:
        level = self.data.setdefault("level", {})
        return level.setdefault("objects", {})

    def add_object(self, category: str, coords: List[int]):
        objects = self.get_objects()
        objects.setdefault(category, []).append(coords)
        if coords:
            self.data["length"] = max(self.get_length(), coords[0] + 1)

    def remove_object(self, category: str, tile_x: int, tile_y: int) -> bool:
        objects = self.get_objects().get(category, [])
        for idx, entry in enumerate(objects):
            if len(entry) >= 2 and entry[0] == tile_x and entry[1] == tile_y:
                objects.pop(idx)
                return True
        return False

    def find_object_at(self, tile_x: int, tile_y: int) -> Optional[Tuple[str, int]]:
        for category, entries in self.get_objects().items():
            width = 1
            height = 1
            if category == "bush":
                width = len(OBJECT_CONFIG["bush"]["sprites"])
            elif category == "cloud":
                width = len(OBJECT_CONFIG["cloud"]["sprites"])
            elif category == "pipe":
                width = 2
            for idx, entry in enumerate(entries):
                if len(entry) < 2:
                    continue
                x0, y0 = entry[0], entry[1]
                if category == "pipe" and len(entry) >= 3:
                    height = entry[2] + 1
                else:
                    height = 1
                if x0 <= tile_x < x0 + width and y0 <= tile_y < y0 + height:
                    return category, idx
        return None

    def remove_object_entry(self, category: str, index: int):
        objects = self.get_objects().get(category)
        if objects and 0 <= index < len(objects):
            objects.pop(index)

    def remove_object_at(self, tile_x: int, tile_y: int) -> bool:
        found = self.find_object_at(tile_x, tile_y)
        if found:
            self.remove_object_entry(*found)
            return True
        return False

    def get_height(self) -> int:
        max_y = MIN_HEIGHT_TILES
        for category, entries in self.get_objects().items():
            for entry in entries:
                if len(entry) < 2:
                    continue
                y = entry[1]
                if category == "pipe" and len(entry) >= 3:
                    y += entry[2]
                max_y = max(max_y, y + 2)
        for entries in self.get_entities().values():
            for entry in entries:
                if len(entry) < 2:
                    continue
                max_y = max(max_y, entry[1] + 2)
        return max_y

    def get_bounds(self) -> Tuple[int, int]:
        min_x: Optional[int] = None
        max_x = 0
        for category, entries in self.get_objects().items():
            if category == "bush":
                width = len(OBJECT_CONFIG["bush"]["sprites"])
            elif category == "cloud":
                width = len(OBJECT_CONFIG["cloud"]["sprites"])
            elif category == "pipe":
                width = 2
            else:
                width = 1
            for entry in entries:
                if len(entry) < 2:
                    continue
                x = entry[0]
                min_x = x if min_x is None else min(min_x, x)
                max_x = max(max_x, x + width)
        layers = self.data.get("level", {}).get("layers", {})
        for layer in layers.values():
            if isinstance(layer, dict) and "x" in layer:
                lx = layer.get("x", [0, 0])
                if isinstance(lx, list) and len(lx) == 2:
                    start, end = lx
                    min_x = start if min_x is None else min(min_x, start)
                    max_x = max(max_x, end)
        for category, entries in self.get_entities().items():
            for entry in entries:
                if len(entry) < 2:
                    continue
                x = entry[0]
                min_x = x if min_x is None else min(min_x, x)
                max_x = max(max_x, x + 1)
        if min_x is None:
            min_x = 0
        return min_x, max_x

    def get_vertical_bounds(self) -> Tuple[int, int]:
        min_y: Optional[int] = None
        max_y = 0
        for category, entries in self.get_objects().items():
            extra = 0
            if category == "pipe":
                extra = 2
            for entry in entries:
                if len(entry) < 2:
                    continue
                y = entry[1]
                min_y = y if min_y is None else min(min_y, y)
                height = entry[2] if category == "pipe" and len(entry) >= 3 else 1 + extra
                max_y = max(max_y, y + max(1, height))
        layers = self.data.get("level", {}).get("layers", {})
        for layer in layers.values():
            if isinstance(layer, dict) and "y" in layer:
                ly = layer.get("y", [0, 0])
                if isinstance(ly, list) and len(ly) == 2:
                    start, end = ly
                    min_y = start if min_y is None else min(min_y, start)
                    max_y = max(max_y, end)
        for entries in self.get_entities().values():
            for entry in entries:
                if len(entry) < 2:
                    continue
                y = entry[1]
                min_y = y if min_y is None else min(min_y, y)
                max_y = max(max_y, y + 1)
        if min_y is None:
            min_y = 0
        return min_y, max_y

    def get_entities(self) -> Dict[str, List[List[int]]]:
        level = self.data.setdefault("level", {})
        return level.setdefault("entities", {})

    def add_entity(self, category: str, coords: List[int]):
        entities = self.get_entities()
        entities.setdefault(category, []).append(coords)
        if coords:
            self.data["length"] = max(self.get_length(), coords[0] + 1)

    def find_entity_at(self, tile_x: int, tile_y: int) -> Optional[Tuple[str, int]]:
        for category, entries in self.get_entities().items():
            for idx, entry in enumerate(entries):
                if len(entry) < 2:
                    continue
                if entry[0] == tile_x and entry[1] == tile_y:
                    return category, idx
        return None

    def remove_entity_entry(self, category: str, index: int):
        entities = self.get_entities().get(category)
        if entities and 0 <= index < len(entities):
            entities.pop(index)

    def remove_entity_at(self, tile_x: int, tile_y: int) -> bool:
        found = self.find_entity_at(tile_x, tile_y)
        if found:
            self.remove_entity_entry(*found)
            return True
        return False


class EditorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Mario Level Editor")
        self.client_dir = resource_path("client")
        self.sprite_library = SpriteLibrary(self.client_dir)
        self.document = LevelDocument()
        self.current_tool: Optional[str] = None
        self.dirty = False

        self.pipe_height_var = tk.IntVar(value=OBJECT_CONFIG["pipe"]["default_height"])

        self.tk_palette_images: Dict[str, ImageTk.PhotoImage] = {}
        self.canvas_image_refs: List[ImageTk.PhotoImage] = []
        self.selection: Optional[Tuple[str, str, int]] = None
        self.selection_rect = None
        self.context_menu = None
        self.history: List[Tuple[Dict, Optional[str]]] = []
        self.history_index = -1

        self._build_ui()
        self._build_palette()
        self.render_level(force_top_left=True)
        self._record_history()

    def _build_ui(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load...", command=self.load_level)
        file_menu.add_command(label="Save", command=self.save_level)
        file_menu.add_command(label="Save As...", command=self.save_level_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", accelerator="Cmd+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Shift+Cmd+Z", command=self.redo)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        self.root.config(menu=menubar)

        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.palette_frame = tk.Frame(main_frame, width=160, padx=6, pady=6)
        self.palette_frame.pack(side=tk.LEFT, fill=tk.Y)

        canvas_frame = tk.Frame(main_frame)
        canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, background=BACKGROUND_COLOR)
        self.h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<Button-1>", self.on_canvas_left_click)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)
        self.canvas.bind("<Motion>", self.on_canvas_motion)

        self.status_var = tk.StringVar()
        status_bar = tk.Label(self.root, textvariable=self.status_var, anchor="w", padx=6)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.selection_info = tk.StringVar(value="Selection: none")
        selection_bar = tk.Label(self.root, textvariable=self.selection_info, anchor="w", padx=6)
        selection_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.pipe_frame = tk.Frame(self.palette_frame, pady=6)
        tk.Label(self.pipe_frame, text="Pipe Height").pack(anchor="w")
        tk.Spinbox(
            self.pipe_frame,
            from_=1,
            to=12,
            textvariable=self.pipe_height_var,
            width=5,
        ).pack(anchor="w")
        self._build_context_menu()

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Delete", command=self.delete_selection)
        self.root.bind_all("<Command-z>", lambda e: self.undo())
        self.root.bind_all("<Command-Z>", lambda e: self.redo())
        self.root.bind_all("<Shift-Command-z>", lambda e: self.redo())
        self.root.bind_all("<Delete>", lambda e: self.delete_selection())
        self.root.bind_all("<BackSpace>", lambda e: self.delete_selection())

    def _build_palette(self):
        for widget in self.palette_frame.winfo_children():
            widget.destroy()

        self.pipe_frame = tk.Frame(self.palette_frame, pady=6)
        tk.Label(self.pipe_frame, text="Pipe Height").pack(anchor="w")
        tk.Spinbox(
            self.pipe_frame,
            from_=1,
            to=12,
            textvariable=self.pipe_height_var,
            width=5,
        ).pack(anchor="w")

        tk.Label(self.palette_frame, text="Tools", font=("Arial", 12, "bold")).pack(anchor="w")
        categories = list(OBJECT_CONFIG.keys()) + list(ENTITY_CONFIG.keys())
        self.palette_buttons = {}
        select_btn = tk.Button(
            self.palette_frame,
            text="Select",
            width=120,
            command=lambda: self.set_tool(None),
        )
        select_btn.pack(fill=tk.X, pady=2)
        self.palette_buttons["__select__"] = select_btn

        for category in categories:
            preview = self._get_palette_image(category)
            if category in OBJECT_CONFIG:
                label = OBJECT_CONFIG[category].get("label", category.title())
            else:
                label = ENTITY_CONFIG[category].get("label", category.title())
            btn = tk.Button(
                self.palette_frame,
                text=label,
                image=preview,
                compound=tk.TOP,
                width=120,
                command=lambda c=category: self.set_tool(c),
            )
            btn.pack(fill=tk.X, pady=2)
            self.palette_buttons[category] = btn

        self.palette_frame.pack_propagate(False)
        self.set_tool(categories[0] if categories else None)
        print("end of _build_palette")

    def _get_palette_image(self, category: str) -> Optional[ImageTk.PhotoImage]:
        if category in self.tk_palette_images:
            return self.tk_palette_images[category]
        cfg = OBJECT_CONFIG.get(category)
        photo = None
        if cfg:
            kind = cfg.get("kind")
            if kind == "single":
                sprites = cfg.get("sprites", [])
                photo = self.sprite_library.build_preview(sprites)
            elif kind == "sequence":
                sprites = cfg.get("sprites", [])
                photo = self.sprite_library.build_preview(sprites)
            elif kind == "pipe":
                sprites = cfg.get("top", [])
                photo = self.sprite_library.build_preview(sprites)
        if photo is None:
            placeholder = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (200, 200, 200, 255))
            photo = ImageTk.PhotoImage(placeholder)
        self.tk_palette_images[category] = photo
        return photo

    def set_tool(self, category: Optional[str]):
        self.current_tool = category
        for cat, btn in self.palette_buttons.items():
            if cat == "__select__":
                btn.configure(relief=tk.SUNKEN if category is None else tk.RAISED)
            else:
                btn.configure(relief=tk.SUNKEN if cat == category else tk.RAISED)
        if self.pipe_frame.winfo_manager():
            self.pipe_frame.pack_forget()
        if category == "pipe":
            self.pipe_frame.pack(anchor="w", pady=6)
        self._update_status()

    def load_level(self):
        initial_dir = resource_path("client", "levels")
        path = filedialog.askopenfilename(
            title="Open Level",
            initialdir=initial_dir,
            filetypes=[("JSON Files", "*.json")],
        )
        if not path:
            print("No path")
            return
        try:
            print("Loading level:", path)
            self.document.load(path)
        except Exception as exc:
            messagebox.showerror("Load Error", f"Failed to load level:\n{exc}")
            print("Error loading level:", exc)
            return
        self.dirty = False
        self._build_palette()
        self.selection = None
        self.render_level(force_top_left=True)
        self._record_history()
        self._update_status()

    def save_level(self):
        try:
            self.document.save()
        except ValueError:
            self.save_level_as()
        except Exception as exc:
            messagebox.showerror("Save Error", f"Unable to save level:\n{exc}")
            return
        else:
            self.dirty = False
            self._update_status()

    def save_level_as(self):
        initial_dir = resource_path("client", "levels")
        path = filedialog.asksaveasfilename(
            title="Save Level As",
            initialdir=initial_dir,
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
        )
        if not path:
            return
        try:
            self.document.save(path)
        except Exception as exc:
            messagebox.showerror("Save Error", f"Unable to save level:\n{exc}")
            return
        self.dirty = False
        self._update_status()

    def render_level(self, force_top_left: bool = False):
        prev_x = self.canvas.xview()
        prev_y = self.canvas.yview()

        self.canvas.delete("all")
        self.canvas_image_refs.clear()

        width = self.document.get_length() * TILE_SIZE
        height = self.document.get_height() * TILE_SIZE
        self.canvas.config(scrollregion=(0, 0, width, height))
        print("width, and height:", width, height)
        self.canvas.create_rectangle(0, 0, width, height, fill=BACKGROUND_COLOR, outline="")

        for x in range(0, width + 1, TILE_SIZE):
            self.canvas.create_line(x, 0, x, height, fill="#d0e7ff")
        for y in range(0, height + 1, TILE_SIZE):
            self.canvas.create_line(0, y, width, y, fill="#d0e7ff")

        self._draw_layers()
        for category, entries in self.document.get_objects().items():
            draw_method = getattr(self, f"draw_{category}", None)
            if draw_method:
                for entry in entries:
                    draw_method(entry)
            else:
                for entry in entries:
                    self._draw_placeholder(entry, category)

        for category, entries in self.document.get_entities().items():
            for entry in entries:
                self.draw_entity(category, entry)

        if force_top_left:
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
        else:
            if prev_x:
                self.canvas.xview_moveto(prev_x[0])
            if prev_y:
                self.canvas.yview_moveto(prev_y[0])
        self._render_selection_highlight()

    # --- Drawing helpers -------------------------------------------------

    def _draw_layers(self):
        layers = self.document.data.get("level", {}).get("layers", {})
        sky = layers.get("sky")
        ground = layers.get("ground")
        if sky:
            self._draw_layer_fill(sky, "sky")
        if ground:
            self._draw_layer_fill(ground, "ground")

    def _draw_layer_fill(self, layer: dict, sprite_name: str):
        x_range = layer.get("x", [0, 0])
        y_range = layer.get("y", [0, 0])
        if not (isinstance(x_range, list) and len(x_range) == 2 and isinstance(y_range, list) and len(y_range) == 2):
            return
        start_x, end_x = x_range
        start_y, end_y = y_range
        photo = self.sprite_library.get_photo(sprite_name)
        if photo is None:
            return
        for tx in range(start_x, end_x):
            for ty in range(start_y, end_y):
                x = tx * TILE_SIZE
                y = ty * TILE_SIZE
                item = self.canvas.create_image(x, y, anchor="nw", image=photo)
                self.canvas_image_refs.append(photo)

    def draw_ground(self, entry: List[int]):
        self._draw_single("ground", entry[0], entry[1])

    def draw_bricks(self, entry: List[int]):
        self._draw_single("bricks", entry[0], entry[1])

    def draw_sky(self, entry: List[int]):
        self._draw_single("sky", entry[0], entry[1])

    def draw_bush(self, entry: List[int]):
        sprites = OBJECT_CONFIG["bush"]["sprites"]
        for idx, name in enumerate(sprites):
            self._draw_single(name, entry[0] + idx, entry[1])

    def draw_cloud(self, entry: List[int]):
        sprites = OBJECT_CONFIG["cloud"]["sprites"]
        for idx, name in enumerate(sprites):
            self._draw_single(name, entry[0] + idx, entry[1])

    def draw_pipe(self, entry: List[int]):
        x, y = entry[0], entry[1]
        height = entry[2] if len(entry) >= 3 else OBJECT_CONFIG["pipe"].get("default_height", 3)
        top = OBJECT_CONFIG["pipe"]["top"]
        body = OBJECT_CONFIG["pipe"]["body"]
        for idx, sprite in enumerate(top):
            self._draw_single(sprite, x + idx, y)
        for h in range(1, max(1, height) + 1):
            for idx, sprite in enumerate(body):
                self._draw_single(sprite, x + idx, y + h)

    def _draw_single(self, sprite_name: str, tile_x: int, tile_y: int):
        photo = self.sprite_library.get_photo(sprite_name)
        if photo is None:
            self._draw_placeholder([tile_x, tile_y], sprite_name)
            return
        x = tile_x * TILE_SIZE
        y = tile_y * TILE_SIZE
        self.canvas.create_image(x, y, anchor="nw", image=photo)
        self.canvas_image_refs.append(photo)

    def draw_entity(self, category: str, entry: List[int]):
        sprite_name = ENTITY_CONFIG.get(category, {}).get("sprite")
        x = entry[0] if len(entry) > 0 else 0
        y = entry[1] if len(entry) > 1 else 0
        if sprite_name:
            photo = self.sprite_library.get_photo(sprite_name)
            if photo is not None:
                self.canvas.create_image(x * TILE_SIZE, y * TILE_SIZE, anchor="nw", image=photo)
                self.canvas_image_refs.append(photo)
                return
        self._draw_placeholder(entry, category)

    def _draw_placeholder(self, entry: List[int], label: str):
        tile_x = entry[0] if len(entry) > 0 else 0
        tile_y = entry[1] if len(entry) > 1 else 0
        x = tile_x * TILE_SIZE
        y = tile_y * TILE_SIZE
        self.canvas.create_rectangle(x, y, x + TILE_SIZE, y + TILE_SIZE, fill="#f0f0f0", outline="#ccc")
        self.canvas.create_text(
            x + TILE_SIZE / 2,
            y + TILE_SIZE / 2,
            text=label[:1].upper(),
            fill="#333",
        )

    # --- Interaction ----------------------------------------------------
    def on_canvas_left_click(self, event):
        tile_x = int(self.canvas.canvasx(event.x) // TILE_SIZE)
        tile_y = int(self.canvas.canvasy(event.y) // TILE_SIZE)
        if self.current_tool is None:
            found = self.document.find_object_at(tile_x, tile_y)
            if found:
                self.selection = ("object", found[0], found[1])
            else:
                entity_found = self.document.find_entity_at(tile_x, tile_y)
                if entity_found:
                    self.selection = ("entity", entity_found[0], entity_found[1])
                else:
                    self.selection = None
            self.render_level()
            self._update_status()
            return
        if self.current_tool in OBJECT_CONFIG:
            cfg = OBJECT_CONFIG[self.current_tool]
            found = self.document.find_object_at(tile_x, tile_y)
            if found:
                self.document.remove_object_entry(*found)
            kind = cfg.get("kind")
            if kind == "pipe":
                height = max(1, self.pipe_height_var.get())
                entry = [tile_x, tile_y, height]
            else:
                entry = [tile_x, tile_y]
            self.document.add_object(self.current_tool, entry)
            self.selection = ("object", self.current_tool, len(self.document.get_objects()[self.current_tool]) - 1)
            self.dirty = True
        elif self.current_tool in ENTITY_CONFIG:
            found_entity = self.document.find_entity_at(tile_x, tile_y)
            if found_entity:
                self.document.remove_entity_entry(*found_entity)
            entry = [tile_x, tile_y]
            self.document.add_entity(self.current_tool, entry)
            self.selection = ("entity", self.current_tool, len(self.document.get_entities()[self.current_tool]) - 1)
            self.dirty = True
        self.render_level()
        if self.dirty:
            self._record_history()
        self._update_status()

    def on_canvas_right_click(self, event):
        tile_x = int(self.canvas.canvasx(event.x) // TILE_SIZE)
        tile_y = int(self.canvas.canvasy(event.y) // TILE_SIZE)
        found = self.document.find_object_at(tile_x, tile_y)
        if found:
            category, index = found
            self.selection = ("object", category, index)
        else:
            entity = self.document.find_entity_at(tile_x, tile_y)
            if entity:
                category, index = entity
                self.selection = ("entity", category, index)
            else:
                self.selection = None
        self.render_level()
        if self.selection:
            try:
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()

    def on_canvas_motion(self, event):
        tile_x = int(self.canvas.canvasx(event.x) // TILE_SIZE)
        tile_y = int(self.canvas.canvasy(event.y) // TILE_SIZE)
        self._update_status((tile_x, tile_y))

    def _update_status(self, cursor: Optional[Tuple[int, int]] = None):
        filename = self.document.path or "(unsaved)"
        mark = "*" if self.dirty else ""
        tool = self.current_tool or "Select"
        cursor_text = ""
        if cursor:
            cursor_text = f"  Cursor: {cursor[0]}, {cursor[1]}"
        self.status_var.set(f"File: {filename}{mark}    Tool: {tool}{cursor_text}")

        if self.selection:
            kind, category, index = self.selection
            entries = (
                self.document.get_objects().get(category)
                if kind == "object"
                else self.document.get_entities().get(category)
            )
            if entries and 0 <= index < len(entries):
                coord = entries[index]
                self.selection_info.set(
                    f"Selection: {kind} {category} at ({coord[0]}, {coord[1]})"
                )
            else:
                self.selection_info.set("Selection: none")
        else:
            self.selection_info.set("Selection: none")

    def _render_selection_highlight(self):
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
            self.selection_rect = None
        if not self.selection:
            return
        kind, category, index = self.selection
        entries = (
            self.document.get_objects().get(category)
            if kind == "object"
            else self.document.get_entities().get(category)
        )
        if not entries or not (0 <= index < len(entries)):
            self.selection = None
            self.selection_info.set("Selection: none")
            return
        entry = entries[index]
        bbox = self._get_entry_bbox(kind, category, entry)
        if not bbox:
            return
        x0, y0, x1, y1 = bbox
        self.selection_rect = self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            outline="#ffcc00",
            width=2,
        )

    def _get_entry_bbox(self, kind: str, category: str, entry: List[int]):
        if len(entry) < 2:
            return None
        x = entry[0] * TILE_SIZE
        y = entry[1] * TILE_SIZE
        if kind == "entity":
            return (x, y, x + TILE_SIZE, y + TILE_SIZE)
        if category == "bush":
            width = len(OBJECT_CONFIG["bush"]["sprites"]) * TILE_SIZE
            return (x, y, x + width, y + TILE_SIZE)
        if category == "cloud":
            width = len(OBJECT_CONFIG["cloud"]["sprites"]) * TILE_SIZE
            return (x, y, x + width, y + TILE_SIZE)
        if category == "pipe":
            height = entry[2] if len(entry) >= 3 else OBJECT_CONFIG["pipe"].get("default_height", 3)
            return (x, y, x + 2 * TILE_SIZE, y + (height + 1) * TILE_SIZE)
        return (x, y, x + TILE_SIZE, y + TILE_SIZE)

    def delete_selection(self):
        if not self.selection:
            return
        kind, category, index = self.selection
        if kind == "object":
            self.document.remove_object_entry(category, index)
        else:
            self.document.remove_entity_entry(category, index)
        self.selection = None
        self.dirty = True
        self.render_level()
        self._record_history()
        self._update_status()

    def _record_history(self):
        state = (copy.deepcopy(self.document.data), self.document.path)
        if self.history_index < len(self.history) - 1:
            self.history = self.history[: self.history_index + 1]
        self.history.append(state)
        self.history_index = len(self.history) - 1
        if len(self.history) > 100:
            self.history = self.history[-100:]
            self.history_index = len(self.history) - 1

    def undo(self):
        if self.history_index <= 0:
            return
        self.history_index -= 1
        self._apply_history_state(self.history[self.history_index])

    def redo(self):
        if self.history_index >= len(self.history) - 1:
            return
        self.history_index += 1
        self._apply_history_state(self.history[self.history_index])

    def _apply_history_state(self, state: Tuple[Dict, Optional[str]]):
        data, path = state
        self.document.data = copy.deepcopy(data)
        self.document.path = path
        self.selection = None
        self.dirty = True
        self._build_palette()
        self.render_level()
        self._update_status()


def main():
    root = tk.Tk()
    root.geometry("1100x720")
    app = EditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
