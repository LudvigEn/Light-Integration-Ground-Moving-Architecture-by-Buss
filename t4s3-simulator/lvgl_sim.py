"""Explicit, small LVGL compatibility layer rendered by Tk, not native LVGL."""
from types import SimpleNamespace

OPA = SimpleNamespace(COVER=255, TRANSP=0)
DIR = SimpleNamespace(LEFT=1, RIGHT=2, TOP=4, BOTTOM=8, ALL=15)
EVENT = SimpleNamespace(CLICKED=1, VALUE_CHANGED=2, ALL=0)
SCROLLBAR_MODE = SimpleNamespace(OFF=0)
ALIGN = SimpleNamespace(CENTER=0, TOP_LEFT=1, TOP_MID=2, BOTTOM_MID=3)
font_montserrat_28 = 28
font_montserrat_20 = 20
font_montserrat_16 = 16
_screen = None
_canvas = None


def color_hex(value):
    return '#%06x' % value


def init():
    pass


def screen_active():
    return _screen


scr_act = screen_active


class obj:
    FLAG = SimpleNamespace(CLICKABLE=1, HIDDEN=2, SCROLLABLE=4)

    def __init__(self, parent=None):
        self.parent = parent
        self.children = []
        if parent:
            parent.children.append(self)
        self.x = self.y = 0
        self.width, self.height = 100, 50
        self.bg, self.fg, self.font = None, '#000000', 16
        self.centered = False
        self.hidden = False
        self.events = []
        self.text = None

    def set_size(self, width, height):
        self.width, self.height = width, height

    def set_width(self, width):
        self.width = width

    def set_height(self, height):
        self.height = height

    def set_pos(self, x, y):
        self.x, self.y = x, y
        self.centered = False

    def center(self):
        self.centered = True

    def align(self, alignment, x=0, y=0):
        if alignment != ALIGN.CENTER:
            raise NotImplementedError('Only ALIGN.CENTER is implemented')
        self.center()
        self.x, self.y = x, y

    def set_style_bg_color(self, color, selector):
        self.bg = color

    def set_style_bg_opa(self, opacity, selector):
        if opacity != OPA.COVER:
            raise NotImplementedError('Only opaque backgrounds are supported')

    def set_style_text_color(self, color, selector):
        self.fg = color

    def set_style_text_font(self, font, selector):
        self.font = font

    def set_scrollbar_mode(self, mode):
        if mode != SCROLLBAR_MODE.OFF:
            raise NotImplementedError('Only hidden scrollbars are supported')

    def add_flag(self, flag):
        if flag & self.FLAG.HIDDEN:
            self.hidden = True

    def remove_flag(self, flag):
        if flag & self.FLAG.HIDDEN:
            self.hidden = False

    def add_event_cb(self, callback, event, data):
        self.events.append((callback, event, data))

    def click(self):
        for callback, event, data in self.events:
            if event in (EVENT.ALL, EVENT.CLICKED):
                callback(SimpleNamespace(get_target=lambda: self,
                                         get_code=lambda: EVENT.CLICKED,
                                         get_user_data=lambda d=data: d))

    def delete(self):
        if self.parent:
            self.parent.children.remove(self)


class label(obj):
    def __init__(self, parent):
        super().__init__(parent)
        self.text = ''

    def set_text(self, text):
        self.text = str(text)

    def get_text(self):
        return self.text


class button(obj):
    def __init__(self, parent):
        super().__init__(parent)
        self.bg = '#dddddd'


btn = button


class tileview(obj):
    def __init__(self, parent):
        super().__init__(parent)
        self.active = (0, 0)

    def add_tile(self, col, row, directions):
        tile = obj(self)
        tile.coord, tile.directions = (col, row), directions
        tile.set_size(self.width, self.height)
        return tile

    def set_tile_by_index(self, col, row, anim=False):
        if (col, row) not in [t.coord for t in self.children]:
            raise ValueError('No tile at this position')
        self.active = (col, row)

    def move(self, dx, dy):
        direction = DIR.RIGHT if dx > 0 else DIR.LEFT if dx < 0 else DIR.BOTTOM if dy > 0 else DIR.TOP
        current = next(t for t in self.children if t.coord == self.active)
        target = (self.active[0] + dx, self.active[1] + dy)
        if current.directions & direction and target in [t.coord for t in self.children]:
            self.active = target


def setup(canvas):
    global _canvas, _screen
    _canvas = canvas
    _screen = obj()
    _screen.set_size(600, 450)
    _screen.bg = '#ffffff'
    return _screen


def render():
    _canvas.delete('all')
    hits = []

    def draw(node, px=0, py=0):
        if node.hidden:
            return
        x, y = px + node.x, py + node.y
        if node.centered and node.parent:
            x += node.parent.width / 2
            y += node.parent.height / 2
            if node.text is None:
                x -= node.width / 2
                y -= node.height / 2
        if node.bg:
            _canvas.create_rectangle(x, y, x + node.width, y + node.height,
                                     fill=node.bg, outline='')
        if node.text is not None:
            _canvas.create_text(x, y, text=node.text, fill=node.fg,
                                font=('Arial', -node.font), anchor='center' if node.centered else 'nw')
        else:
            hits.append((x, y, x + node.width, y + node.height, node))
        for child in node.children:
            if isinstance(node, tileview) and child.coord != node.active:
                continue
            draw(child, x, y)
    draw(_screen)
    return hits


def tileviews(node=None):
    node = node or _screen
    if isinstance(node, tileview):
        yield node
    for child in node.children:
        yield from tileviews(child)
