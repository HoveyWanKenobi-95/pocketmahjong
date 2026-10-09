"""Pocket Mahjong: a compact, no-assets Kivy Mahjong Solitaire prototype."""
from __future__ import annotations
import random
import json
import os
from collections import Counter
from pathlib import Path
from kivy.uix.image import Image as KivyImage
from dataclasses import dataclass
from functools import partial
from kivy.app import App
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Line, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.clock import Clock
from kivy.uix.popup import Popup
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
import webbrowser

WEBSITE_URL = "https://hoveywankenobi-95.github.io"
TIP_URL = "https://buymeacoffee.com/hoveybits"
PRIVACY_URL = "https://hoveywankenobi-95.github.io/privacy.html"

# Tile positions use half-tile coordinates to allow staggered layers.
# Each tile occupies a 2x2 square in this coordinate system.
@dataclass(frozen=True)
class Position:
    x: int
    y: int
    z: int


def layer_rect(w, h, z, x=0, y=0):
    return [Position(x + 2 * col, y + 2 * row, z)
            for row in range(h) for col in range(w)]


def rectangle():
    return layer_rect(12, 8, 0)


def turtle():
    return (layer_rect(12, 8, 0) + layer_rect(10, 6, 1, 2, 2)
            + layer_rect(8, 4, 2, 4, 4) + layer_rect(4, 2, 3, 8, 6))


def pyramid():
    return (layer_rect(12, 8, 0) + layer_rect(10, 6, 1, 2, 2)
            + layer_rect(8, 4, 2, 4, 4) + layer_rect(6, 2, 3, 6, 6))


def fortress():
    base = layer_rect(12, 8, 0)
    walls = [p for p in layer_rect(10, 6, 1, 2, 2)
             if p.x in (2, 20) or p.y in (2, 12)]
    return base + walls


def bridge():
    return layer_rect(12, 8, 0) + layer_rect(8, 2, 1, 4, 6)


def towers():
    base = layer_rect(12, 8, 0)
    corners = [(0, 0), (16, 0), (0, 8), (16, 8)]
    return base + [p for x, y in corners for p in layer_rect(4, 4, 1, x, y)]


def steps():
    return (layer_rect(12, 8, 0) + layer_rect(8, 6, 1, 4, 2)
            + layer_rect(4, 4, 2, 8, 4))


# Phone-friendly boards use fewer columns, so individual tiles are larger.
# These are separate named layouts so saved games remain valid across rotation.
def pocket_rectangle():
    return layer_rect(6, 8, 0)


def pocket_turtle():
    return layer_rect(6, 8, 0) + layer_rect(4, 6, 1, 2, 2) + layer_rect(2, 4, 2, 4, 4)


def pocket_pyramid():
    return layer_rect(6, 8, 0) + layer_rect(4, 6, 1, 2, 2) + layer_rect(2, 2, 2, 4, 6)


def pocket_bridge():
    return layer_rect(6, 8, 0) + layer_rect(4, 2, 1, 2, 6)


LAYOUTS = {
    'Rectangle': rectangle, 'Turtle': turtle, 'Pyramid': pyramid,
    'Fortress': fortress, 'Bridge': bridge, 'Four Towers': towers,
    'Steps': steps,
    'Pocket Rectangle': pocket_rectangle, 'Pocket Turtle': pocket_turtle,
    'Pocket Pyramid': pocket_pyramid, 'Pocket Bridge': pocket_bridge,
}

FACES=['1B','1C','1D','2B','2C','2D','3B','3C',
    '3D','4B','4C','4D','5B','5C','5D','6B',
    '6C','6D','7B','7C','7D','8B','8C','8D',
    '9B','9C','9D','Au','Bm','Ch','E','G','N',
    'Or','Pl','R','S','Sp','Su','W','Wh','Wi']


def overlap(a,b):
    return abs(a.x-b.x)<2 and abs(a.y-b.y)<2


def is_free(p, active):
    if any(q.z>p.z and overlap(p,q) for q in active):
        return False
    left=any(q.z==p.z and abs(q.y-p.y)<2 and q.x==p.x-2 for q in active)
    right=any(q.z==p.z and abs(q.y-p.y)<2 and q.x==p.x+2 for q in active)
    return not (left and right)


def generate(positions, rng):
    """Construct a board with a recorded legal solution from its geometry.

    Each generated pair is assigned the same face, and pairs can be removed
    in generation order. Retry randomized removal paths that reach a dead end.
    This guarantees at least one solution from the initial board, not that
    every possible player choice remains solvable.
    """
    if len(positions) % 2:
        raise ValueError('Layout must contain an even number of tiles')
    for attempt in range(300):
        remaining = set(positions)
        pairs = []
        while remaining:
            free = [p for p in remaining if is_free(p, remaining)]
            if len(free) < 2:
                break
            a, b = rng.sample(free, 2)
            pairs.append((a, b))
            remaining.remove(a)
            remaining.remove(b)
        if not remaining:
            # Balanced identities (even counts), with random pair placement.
            pair_faces = [FACES[i % len(FACES)] for i in range(len(pairs))]
            rng.shuffle(pair_faces)
            board = {}
            for (a, b), face in zip(pairs, pair_faces):
                board[a] = face
                board[b] = face
            return board
    raise ValueError('Unable to generate a solvable board for this layout')


class TileButton(Button):
    def __init__(self, face, depth=0, **kwargs):
        super().__init__(text=face, font_size='16sp', bold=True,
                         background_normal='', background_down='',
                         background_color=(0,0,0,0), color=(0.1,0.16,0.22,1), **kwargs)
        self.face=face
        self.depth=depth
        tile_file=Path(__file__).resolve().parent / 'assets' / 'tiles' / f'{face}.png'
        self.has_artwork = tile_file.is_file()
        if self.has_artwork:
            self.text=''
            self.tile_image=KivyImage(source=str(tile_file),fit_mode='contain',size_hint=(None,None))
            self.add_widget(self.tile_image)
        self.selected=False
        self.available=True
        with self.canvas.before:
            # Artwork PNGs contain their own complete tile body and shadow.
            # Legacy fallback geometry is transparent whenever artwork exists.
            # Shadow is behind the tile; it grows slightly with stack height.
            self.shadow_color=Color(0.015, 0.025, 0.035, 0.40 if depth else 0.24)
            self.shadow=RoundedRectangle(radius=[dp(6)])
            # Visible dark bottom/right edge gives stacked tiles physical depth.
            self.edge_color=Color(0.48, 0.43, 0.34, 1)
            self.edge=RoundedRectangle(radius=[dp(5)])
            self.fill=Color(0.94,0.89,0.75,1)
            self.bg=RoundedRectangle(radius=[dp(5)])
            self.stroke_color=Color(0.35,0.30,0.23,1)
            self.stroke=Line(rounded_rectangle=(0,0,1,1,dp(5)),width=1)
        # Draw selection tint above the artwork (20% opaque blue).
        with self.canvas.after:
            self.blocked_color = Color(0.08, 0.10, 0.10, 0)
            self.blocked_rect = RoundedRectangle(radius=[dp(5)])
            self.highlight_color = Color(0.10, 0.45, 1.0, 0)
            self.highlight_rect = RoundedRectangle(radius=[dp(5)])
        self.bind(pos=self.redraw,size=self.redraw)
        self.redraw()

    def redraw(self,*_):
        self.fill.rgba = ((0, 0, 0, 0) if self.has_artwork else
                          ((0.94,0.89,0.75,1) if self.available else (0.57,0.57,0.53,1)))
        self.shadow_color.rgba = (0, 0, 0, 0) if self.has_artwork else (0.015, 0.025, 0.035, 0.40 if self.depth else 0.24)
        self.edge_color.rgba = (0, 0, 0, 0) if self.has_artwork else (0.48, 0.43, 0.34, 1)
        self.stroke_color.rgba = (0, 0, 0, 0) if self.has_artwork else (0.35, 0.30, 0.23, 1)
        if hasattr(self,'tile_image'):
            self.tile_image.pos=self.pos
            # Maintain the source aspect ratio, including in the storage tray.
            texture = self.tile_image.texture
            ratio = (texture.width / texture.height) if texture and texture.height else 256 / 336
            width = min(self.width, self.height * ratio)
            height = width / ratio
            self.tile_image.size = (width, height)
            self.tile_image.pos = (self.center_x-width/2, self.center_y-height/2)
            self.tile_image.opacity=1  # Never fade the PNG: overlapping tiles must remain opaque
        self.blocked_color.rgba=(0.08, 0.10, 0.10, 0.25) if not self.available else (0, 0, 0, 0)
        self.blocked_rect.pos=self.pos
        self.blocked_rect.size=self.size
        self.highlight_color.rgba=(0.10, 0.45, 1.0, 0.20) if self.selected else (0.10, 0.45, 1.0, 0)
        self.highlight_rect.pos=self.pos
        self.highlight_rect.size=self.size
        depth_px=dp(2.5 + min(self.depth, 5) * 1.1)
        self.shadow.pos=(self.x+dp(3)+self.depth*dp(1.5), self.y-depth_px-dp(2))
        self.shadow.size=(self.width, self.height)
        self.edge.pos=(self.x+dp(1.5), self.y-depth_px)
        self.edge.size=self.size
        self.bg.pos=self.pos
        self.bg.size=self.size
        self.stroke.rounded_rectangle=(self.x,self.y,max(1,self.width),max(1,self.height),dp(5))


class Board(Widget):
    """Retain tile widgets; only create/remove them when the board changes."""
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self.buttons = {}
        self._free_positions = set()
        self.bind(size=self.refresh, pos=self.refresh)

    def refresh(self, *_):
        tiles = self.game.tiles
        # Reuse existing buttons, including their loaded image textures.
        for p in list(self.buttons):
            if p not in tiles or self.buttons[p].face != tiles[p]:
                self.remove_widget(self.buttons.pop(p))
        for p in sorted(tiles, key=lambda p: (p.z, p.y, p.x)):
            if p not in self.buttons:
                btn = TileButton(tiles[p], depth=p.z, size_hint=(None, None))
                btn.bind(on_release=partial(self.game.select_board, p))
                self.buttons[p] = btn
                self.add_widget(btn)
        if not tiles or self.width < 10 or self.height < 10:
            return
        geometry = LAYOUTS[self.game.layout_name]()
        minx = min(p.x for p in geometry); miny = min(p.y for p in geometry)
        maxx = max(p.x + 2 for p in geometry); maxy = max(p.y + 2 for p in geometry)
        # PNG tile art is 256 x 336 (width x height). Fit the FULL PNG,
        # including its baked-in left/bottom 3D edge, in each grid cell.
        # No second Kivy tile background or additional image padding is needed.
        aspect_height = 336 / 256
        columns = (maxx - minx) / 2
        rows = (maxy - miny) / 2
        max_depth = max(p.z for p in geometry)
        layer_offset = dp(5)
        depth_shift = layer_offset * max_depth
        margin = dp(6)
        tw = min((self.width - 2 * margin - depth_shift) / columns,
                 (self.height - 2 * margin - depth_shift) / (rows * aspect_height))
        tw = max(dp(3), tw)
        th = tw * aspect_height
        # A tiny gutter prevents texture edges from bleeding into neighbors.
        # Change to dp(0) if you want the tile canvases to touch exactly.
        gutter = dp(0.5)
        tile_w = max(dp(2), tw - gutter)
        tile_h = tile_w * aspect_height
        total_w = columns * tw + depth_shift
        total_h = rows * th + depth_shift
        origin_x = self.x + (self.width - total_w) / 2
        origin_y = self.y + (self.height - total_h) / 2
        for p, btn in self.buttons.items():
            btn.size = (tile_w, tile_h)
            btn.pos = (origin_x + (p.x - minx) * tw / 2 + p.z * layer_offset,
                       origin_y + (p.y - miny) * th / 2 + p.z * layer_offset)
        self.update_states()

    def update_states(self):
        self._free_positions = {p for p in self.game.tiles if is_free(p, self.game.tiles)}
        self.update_selection()

    def update_selection(self):
        selected = self.game.selected
        for p, btn in self.buttons.items():
            available = p in self._free_positions
            highlighted = selected == ('board', p)
            if btn.available != available or btn.selected != highlighted:
                btn.available = available
                btn.selected = highlighted
                btn.redraw()


# A compact live geometry preview. No image assets or screenshots required.
class LayoutPreview(Widget):
    def __init__(self, layout_name, **kwargs):
        super().__init__(**kwargs)
        self.layout_name = layout_name
        self.bind(pos=self.draw_preview, size=self.draw_preview)

    def draw_preview(self, *_):
        self.canvas.clear()
        positions = LAYOUTS[self.layout_name]()
        minx=min(p.x for p in positions); maxx=max(p.x+2 for p in positions)
        miny=min(p.y for p in positions); maxy=max(p.y+2 for p in positions)
        scale=min(max(1,self.width- dp(20))/(maxx-minx),
                  max(1,self.height-dp(18))/(maxy-miny))
        ox=self.center_x-(maxx-minx)*scale/2
        oy=self.center_y-(maxy-miny)*scale/2
        with self.canvas:
            for pos in sorted(positions,key=lambda p:(p.z,p.y,p.x)):
                x=ox+(pos.x-minx)*scale+pos.z*dp(1.7)
                y=oy+(pos.y-miny)*scale+pos.z*dp(1.7)
                Color(0.03,0.09,0.12,0.20)
                RoundedRectangle(pos=(x+dp(1.5),y-dp(1.5)),size=(scale*1.85,scale*1.85),radius=[dp(2)])
                Color(*[(0.91,0.95,0.93,1),(0.72,0.85,0.84,1),(0.47,0.72,0.73,1),(0.24,0.57,0.65,1)][min(pos.z,3)])
                RoundedRectangle(pos=(x,y),size=(scale*1.85,scale*1.85),radius=[dp(2)])


class FlatButton(Button):
    def __init__(self, accent=False, **kwargs):
        super().__init__(background_normal='',background_down='',
                         background_color=(0,0,0,0), color=(0.94,0.97,0.97,1),
                         bold=True, **kwargs)
        self.accent=accent
        with self.canvas.before:
            self.surface_color=Color(*( (0.10,0.57,0.62,1) if accent else (0.17,0.27,0.31,1)))
            self.surface=RoundedRectangle(radius=[dp(11)])
        self.bind(pos=self._paint,size=self._paint,state=self._paint)
        self._paint()

    def _paint(self,*_):
        self.surface.pos=self.pos;self.surface.size=self.size
        self.surface_color.rgba=((0.13,0.67,0.70,1) if self.accent else (0.22,0.34,0.39,1)) if self.state=='down' else ((0.10,0.57,0.62,1) if self.accent else (0.17,0.27,0.31,1))


class MahjongGame(BoxLayout):
    def __init__(self,**kwargs):
        super().__init__(orientation='vertical',padding=dp(7),spacing=dp(5),**kwargs)
        self.rng=random.Random()
        # Default to a narrow board on portrait phones; saved games take priority.
        portrait_phone = Window.width < Window.height and Window.width / max(dp(1), .01) < 650
        self.layout_name='Pocket Turtle' if portrait_phone else 'Turtle'
        self.capacity=4
        self.tiles={}
        self.storage=[]
        self.selected=None
        self.history=[]
        self.win_popup=None
        self.about_popup=None
        self._restoring=False
        self._save_trigger = Clock.create_trigger(lambda dt: self.save_game(), 0.25)
        self.save_path=Path(App.get_running_app().user_data_dir) / 'savegame.json'
        self.build_ui()
        Window.bind(size=self.on_window_size)
        self.on_window_size()
        if not self.load_game():
            self.new_game()

    def on_window_size(self, *_):
        # Physical Android pixels can be very dense: use dp for usable dimensions.
        screen_w = Window.width / max(dp(1), 0.01)
        screen_h = Window.height / max(dp(1), 0.01)
        compact = screen_w < 650
        self.ui_scale = 0.90 if compact else min(1.25, max(0.9, screen_w / 850))
        self.padding = dp(5 if compact else 9)
        self.spacing = dp(3 if compact else 8)
        self.toolbar.height = dp(88 if compact else 54)
        self.toolbar.orientation = 'vertical' if compact else 'horizontal'
        for row in (self.toolbar_row1, self.toolbar_row2):
            row.spacing = dp(4 if compact else 7)
        if compact:
            # Two independent rows, avoiding seven narrow buttons on a phone.
            if self.toolbar_row2.parent is not self.toolbar:
                self.toolbar.add_widget(self.toolbar_row2)
        elif self.toolbar_row2.parent is self.toolbar:
            self.toolbar.remove_widget(self.toolbar_row2)
        if not compact:
            # Desktop toolbar contains all controls in one row.
            for w in list(self.toolbar_row2.children)[::-1]:
                self.toolbar_row2.remove_widget(w)
                self.toolbar_row1.add_widget(w)
        else:
            # Restore compact arrangement if orientation changed.
            for w in self.second_row_widgets:
                if w.parent is self.toolbar_row1:
                    self.toolbar_row1.remove_widget(w)
                    self.toolbar_row2.add_widget(w)
        self.info.height = dp(23 if compact else 33)
        self.info.font_size = dp(12 if compact else 17)
        self.bottom.height = dp(65 if compact else 94)
        self.bottom.spacing = dp(4 if compact else 8)
        self.store_button.size_hint_x = .27 if compact else .24
        self.storage_bar.size_hint_x = .73 if compact else .76
        self.storage_bar.spacing = dp(2 if compact else 5)
        for button in self.controls:
            button.font_size = dp(12 if compact else 15)
        self.store_button.font_size = dp(12 if compact else 15)
        self.storage_spinner.font_size = dp(12 if compact else 15)
        Clock.schedule_once(lambda dt: self.board.refresh(), 0)

    def build_ui(self):
        from kivy.uix.spinner import Spinner
        self.controls = []
        self.toolbar = BoxLayout(orientation='horizontal', size_hint_y=None,
                                 height=dp(54), spacing=dp(4))
        self.toolbar_row1 = BoxLayout(spacing=dp(4))
        self.toolbar_row2 = BoxLayout(spacing=dp(4))

        def control(title, fn, accent=False):
            button = FlatButton(text=title, accent=accent)
            button.bind(on_release=lambda _, f=fn: f())
            self.controls.append(button)
            return button

        self.toolbar_row1.add_widget(control('Layouts', self.choose_layout, True))
        self.toolbar_row1.add_widget(control('Random', self.random_layout))
        self.storage_spinner = Spinner(
            text='Storage: 4', values=['Storage: 0', 'Storage: 2',
                                      'Storage: 4', 'Storage: 8'],
            background_normal='', background_color=(.17,.27,.31,1),
            color=(1,1,1,1))
        self.storage_spinner.bind(text=lambda _, v: self.set_capacity(int(v.split(': ')[1])))
        self.toolbar_row1.add_widget(self.storage_spinner)
        self.second_row_widgets = [
            control('New', self.new_game),
            control('Restart', self.restart),
            control('Undo', self.undo),
            control('About', self.show_about),
        ]
        for button in self.second_row_widgets:
            self.toolbar_row2.add_widget(button)
        self.toolbar.add_widget(self.toolbar_row1)
        self.add_widget(self.toolbar)

        self.info = Label(size_hint_y=None, height=dp(33), font_size=dp(17),
                          bold=True, color=(.87,.95,.95,1), halign='center', shorten=True)
        self.info.bind(size=lambda w, _: setattr(w, 'text_size', (w.width-dp(10), None)))
        self.add_widget(self.info)
        self.board = Board(self, size_hint=(1, 1))
        self.add_widget(self.board)
        self.bottom = BoxLayout(size_hint_y=None, height=dp(94), spacing=dp(4))
        self.store_button = FlatButton(text='Store tile', accent=True, size_hint_x=.24)
        self.store_button.bind(on_release=lambda _: self.store_selected())
        self.bottom.add_widget(self.store_button)
        self.storage_bar = GridLayout(cols=8, spacing=dp(3), size_hint_x=.76)
        self.bottom.add_widget(self.storage_bar)
        self.add_widget(self.bottom)

    def choose_layout(self):
        # Phone-friendly cards: two-line labels with bounded text regions.
        scale = getattr(self, 'ui_scale', 1)
        content = BoxLayout(orientation='vertical', padding=dp(10)*scale,
                            spacing=dp(8)*scale)
        heading = Label(text='CHOOSE A LAYOUT', font_size=dp(21)*scale,
                        bold=True, color=(.92,.98,.98,1),
                        size_hint_y=None, height=dp(42)*scale)
        content.add_widget(heading)
        scroll = ScrollView(do_scroll_x=False)
        # One column on especially narrow phones; two on normal phones.
        usable_width = Window.width / max(dp(1), .01)
        cols = 1 if usable_width < 340 else (2 if usable_width < 1000 else 3)
        grid = GridLayout(cols=cols, spacing=dp(8)*scale,
                          padding=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        popup = Popup(title='', separator_height=0, background='',
                      background_color=(0,0,0,0), content=content,
                      size_hint=(.94,.91), auto_dismiss=True)

        def fit_button_text(button, inset=8):
            # Kivy Buttons don't wrap automatically: constrain the text width.
            button.halign = 'center'
            button.valign = 'middle'
            button.bind(size=lambda w, *_: setattr(
                w, 'text_size', (max(dp(10), w.width - dp(inset)*2),
                                max(dp(10), w.height - dp(4)))))
            button.text_size = (max(dp(10), button.width - dp(inset)*2),
                                max(dp(10), button.height - dp(4)))

        names = list(LAYOUTS)
        if Window.width < Window.height:
            names.sort(key=lambda name: (not name.startswith('Pocket '), name))
        for name in names:
            positions = LAYOUTS[name]()
            layers = max(p.z for p in positions) + 1
            card = BoxLayout(orientation='vertical', spacing=dp(4)*scale,
                             padding=dp(7)*scale, size_hint_y=None,
                             height=dp(188)*scale)
            with card.canvas.before:
                Color(.15,.25,.29,1)
                bg = RoundedRectangle(radius=[dp(12)])
            card.bind(pos=lambda w, _, shape=bg: setattr(shape, 'pos', w.pos),
                      size=lambda w, _, shape=bg: setattr(shape, 'size', w.size))
            card.add_widget(LayoutPreview(name, size_hint_y=1))
            # Name and tile count on separate lines to avoid overflow.
            details = f'{len(positions)} tiles · {layers} layer' + ('s' if layers != 1 else '')
            select = FlatButton(text=f'{name}\n{details}',
                                accent=(name == self.layout_name),
                                size_hint_y=None, height=dp(52)*scale,
                                font_size=dp(12)*scale, line_height=1.12)
            fit_button_text(select, inset=5)
            select.bind(on_release=lambda _, n=name:
                        (popup.dismiss(), self.set_layout(n, force=True)))
            card.add_widget(select)
            grid.add_widget(card)
        scroll.add_widget(grid)
        content.add_widget(scroll)

        actions = BoxLayout(size_hint_y=None, height=dp(52)*scale,
                            spacing=dp(8)*scale)
        cancel = FlatButton(text='Close', font_size=dp(14)*scale,
                            size_hint_x=.30)
        fit_button_text(cancel)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        random_btn = FlatButton(text='Surprise me\nRandom layout', accent=True,
                                font_size=dp(13)*scale, line_height=1.12,
                                size_hint_x=.70)
        fit_button_text(random_btn)
        random_btn.bind(on_release=lambda *_:
                        (popup.dismiss(), self.random_layout()))
        actions.add_widget(cancel)
        actions.add_widget(random_btn)
        content.add_widget(actions)
        popup.open()

    def random_layout(self):
        self.set_layout(self.rng.choice(list(LAYOUTS)),force=True)

    def set_layout(self,value,force=False):
        if force or value!=self.layout_name:
            self.layout_name=value
            self.new_game()

    def set_capacity(self,value):
        if value!=self.capacity:
            self.capacity=value
            self.new_game()

    def new_game(self,*_):
        self.close_win_popup()
        try:
            self.tiles=generate(LAYOUTS[self.layout_name](),self.rng)
        except ValueError as exc:
            self.info.text=str(exc)
            return
        self.initial=self.tiles.copy()
        self.storage=[]
        self.selected=None
        self.history=[]
        self.update_ui()
        self.save_game()

    def restart(self,*_):
        self.close_win_popup()
        self.tiles=self.initial.copy()
        self.storage=[]
        self.selected=None
        self.history=[]
        self.update_ui()
        self.save_game()

    def snapshot(self):
        self.history.append((self.tiles.copy(),self.storage.copy()))

    def undo(self,*_):
        self.close_win_popup()
        if self.history:
            self.tiles,self.storage=self.history.pop()
            self.selected=None
            self.update_ui()
            self.save_game()

    def select_board(self,p,*_):
        if p not in self.tiles or not is_free(p,self.tiles):
            return
        self.select(('board',p),self.tiles[p])

    def select_storage(self,index,*_):
        if index<len(self.storage):
            self.select(('storage',index),self.storage[index])

    def select(self, location, face):
        changed_board = False
        if self.selected == location:
            self.selected = None
        elif self.selected is not None:
            kind, key = self.selected
            first = self.tiles.get(key) if kind == 'board' else (self.storage[key] if key < len(self.storage) else None)
            if first == face:
                self.snapshot()
                for k, idx in sorted([self.selected, location],
                                     key=lambda x: (x[0] != 'storage', -x[1] if x[0] == 'storage' else 0)):
                    if k == 'board':
                        self.tiles.pop(idx, None)
                    else:
                        self.storage.pop(idx)
                self.selected = None
                changed_board = True
            else:
                self.selected = location
        else:
            self.selected = location
        if changed_board:
            self.update_ui()
            self._save_trigger()
        else:
            self.board.update_selection()
            self.update_storage_selection()


    def store_selected(self):
        if not self.selected or self.selected[0]!='board' or len(self.storage)>=self.capacity:
            return
        p=self.selected[1]
        if p in self.tiles and is_free(p,self.tiles):
            self.snapshot()
            self.storage.append(self.tiles.pop(p))
            self.selected=None
            self.update_ui()
            self._save_trigger()

    def update_storage_selection(self):
        for i, b in enumerate(self.storage_bar.children[::-1]):
            if isinstance(b, TileButton):
                selected = self.selected == ('storage', i)
                if b.selected != selected:
                    b.selected = selected
                    b.redraw()

    def update_ui(self):
        self.board.refresh()
        self.storage_bar.clear_widgets()
        for i in range(self.capacity):
            if i<len(self.storage):
                b=TileButton(self.storage[i])
                b.selected=self.selected==('storage',i)
                b.redraw()
                b.bind(on_release=partial(self.select_storage,i))
            else:
                b=FlatButton(text='·',disabled=True)
            self.storage_bar.add_widget(b)
        free=len(self.board._free_positions)
        total=len(self.tiles)+len(self.storage)
        if total==0:
            status=f'{self.layout_name} | You win!'
        elif free==0 and not self._has_storage_pair():
            status=f'{self.layout_name} | No available moves — Undo or restart'
        else:
            status=f'{self.layout_name} | {total} tiles left | {free} free | Holding {len(self.storage)}/{self.capacity}'
        self.info.text=status
        if total == 0 and self.win_popup is None:
            self.show_win_popup()

    def close_win_popup(self):
        if self.win_popup is not None:
            popup=self.win_popup
            self.win_popup=None
            popup.dismiss()

    def show_win_popup(self):
        content=BoxLayout(orientation='vertical', padding=dp(22), spacing=dp(16))
        title=Label(text='YOU WON!', bold=True, font_size=dp(34)*getattr(self,'ui_scale',1), color=(0.35,0.88,0.78,1))
        subtitle=Label(text='You cleared every tile!', font_size='18sp')
        again=FlatButton(text='Play Again', accent=True, font_size=dp(18)*getattr(self,'ui_scale',1), size_hint_y=None, height=dp(52))
        content.add_widget(title)
        content.add_widget(subtitle)
        content.add_widget(again)
        popup=Popup(title='Victory', content=content, size_hint=(0.8,0.65),
                    auto_dismiss=False)
        self.win_popup=popup
        again.bind(on_release=lambda *_:self.new_game())
        popup.open()

    def show_about(self, *_):
        scale=getattr(self,'ui_scale',1)
        content=BoxLayout(orientation='vertical',padding=dp(18),spacing=dp(12))
        for message, size, bold in [
            ('Pocket Mahjong',25,True),
            ('Just Mahjong. No ads.',19,True),
            ('Made for people who want to enjoy Mahjong without ads, accounts, tracking, or interruptions.',16,False),
            ('Everything is free. Tips are completely optional and never unlock features.',15,False),
            ('Support the Developer',19,True),
            ('A tip link is available on my website. I may add add one here later, after checking the current Google Play payment rules.',14,False),
        ]:
            label=Label(text=message,font_size=dp(size)*scale,bold=bold,
                        color=(.89,.96,.95,1),halign='center',valign='middle',size_hint_y=None,
                        height=dp(48 if len(message)<30 else 88)*scale)
            label.bind(size=lambda w,_:setattr(w,'text_size',(w.width-dp(8),None)))
            content.add_widget(label)
        close=FlatButton(text='Back to game',accent=True,size_hint_y=None,height=dp(48)*scale)
        content.add_widget(close)
        popup=Popup(title='About',content=content,size_hint=(.88,.86))
        close.bind(on_release=lambda *_:popup.dismiss())
        website_btn = FlatButton(
            text="Visit HoveyBits",
            size_hint_y=None,
            height=dp(48)
        )
        website_btn.bind(
            on_release=lambda *_: webbrowser.open(WEBSITE_URL)
        )

        privacy_btn = FlatButton(
            text="Privacy Policy",
            size_hint_y=None,
            height=dp(48)
        )
        privacy_btn.bind(
            on_release=lambda *_: webbrowser.open(PRIVACY_URL)
        )

        content.add_widget(website_btn)
        content.add_widget(privacy_btn)
        popup.open()

    @staticmethod
    def _encode_board(board):
        return [[p.x,p.y,p.z,face] for p,face in sorted(board.items(),key=lambda kv:(kv[0].z,kv[0].y,kv[0].x))]

    @staticmethod
    def _decode_board(rows):
        if not isinstance(rows,list):
            raise ValueError('Invalid board')
        board={}
        for row in rows:
            if not isinstance(row,list) or len(row)!=4:
                raise ValueError('Invalid tile record')
            x,y,z,face=row
            if type(x)!=int or type(y)!=int or type(z)!=int or face not in FACES:
                raise ValueError('Invalid tile')
            pos=Position(x,y,z)
            if pos in board:
                raise ValueError('Duplicate tile')
            board[pos]=face
        return board

    def save_game(self):
        if self._restoring:
            return
        state={
            'version':1,'layout':self.layout_name,'capacity':self.capacity,
            'tiles':self._encode_board(self.tiles),
            'initial':self._encode_board(self.initial),
            'storage':list(self.storage),
            'history':[
                {'tiles':self._encode_board(board),'storage':list(storage)}
                for board,storage in self.history[-200:]
            ],
        }
        try:
            self.save_path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.save_path.with_suffix('.tmp')
            temp.write_text(json.dumps(state,separators=(',',':')),encoding='utf-8')
            os.replace(temp,self.save_path)
        except OSError as exc:
            print('Unable to save game:',exc)

    def load_game(self):
        if not self.save_path.is_file():
            return False
        try:
            state=json.loads(self.save_path.read_text(encoding='utf-8'))
            layout=state['layout'];capacity=state['capacity']
            if state.get('version')!=1 or layout not in LAYOUTS or capacity not in (0,2,4,8):
                return False
            initial=self._decode_board(state['initial'])
            tiles=self._decode_board(state['tiles'])
            geometry=set(LAYOUTS[layout]())
            if set(initial)!=geometry or not set(tiles).issubset(geometry):
                return False
            if any(initial[p]!=face for p,face in tiles.items()):
                return False
            storage=state['storage']
            if not isinstance(storage,list) or len(storage)>capacity or any(f not in FACES for f in storage):
                return False
            history=[]
            for entry in state.get('history',[])[-200:]:
                old_board=self._decode_board(entry['tiles'])
                old_storage=entry['storage']
                if not set(old_board).issubset(geometry) or any(initial[p]!=face for p,face in old_board.items()):
                    return False
                if not isinstance(old_storage,list) or len(old_storage)>capacity or any(f not in FACES for f in old_storage):
                    return False
                history.append((old_board,old_storage))
            self._restoring=True
            self.layout_name=layout;self.capacity=capacity
            self.initial=initial;self.tiles=tiles;self.storage=storage
            self.history=history;self.selected=None
            self.storage_spinner.text=f'Storage: {capacity}'
            self.update_ui()
            self._restoring=False
            return True
        except (ValueError,KeyError,TypeError,OSError,IndexError) as exc:
            print('Could not restore saved game:',exc)
            self._restoring=False
            return False

    def _has_storage_pair(self):
        faces=self.storage+[self.tiles[p] for p in self.tiles if is_free(p,self.tiles)]
        return len(faces)!=len(set(faces))

class PocketMahjong(App):
    def on_pause(self):
        if self.root:
            self.root.save_game()
        return True

    def on_stop(self):
        if self.root:
            self.root.save_game()

    def build(self):
        self.title='Pocket Mahjong'
        Window.clearcolor=(.10,.16,.18,1)
        return MahjongGame()

if __name__=='__main__':
    PocketMahjong().run()
