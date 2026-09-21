"""Explicit, small LVGL compatibility layer rendered by Tk, not native LVGL."""
from types import SimpleNamespace

OPA = SimpleNamespace(COVER=255, TRANSP=0)
DIR = SimpleNamespace(NONE=0, LEFT=1, RIGHT=2, TOP=4, BOTTOM=8, HOR=3, VER=12, ALL=15)
EVENT = SimpleNamespace(CLICKED=1, VALUE_CHANGED=2, ALL=0)
STATE = SimpleNamespace(DEFAULT=0, CHECKED=1, DISABLED=2)
ANIM = SimpleNamespace(OFF=0, ON=1)
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
        self.flags = self.FLAG.SCROLLABLE
        self.state = STATE.DEFAULT
        self.scroll_y = 0
        self.scroll_dir = DIR.ALL
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

    def set_style_pad_all(self, padding, selector):
        # The renderer already uses zero padding and no theme borders.
        if padding != 0 or selector != 0:
            raise NotImplementedError('Only zero padding on the default selector is supported')

    def set_style_border_width(self, width, selector):
        if width != 0 or selector != 0:
            raise NotImplementedError('Only zero border width on the default selector is supported')

    def get_parent(self):
        return self.parent

    def set_scrollbar_mode(self, mode):
        if mode != SCROLLBAR_MODE.OFF:
            raise NotImplementedError('Only hidden scrollbars are supported')

    def add_flag(self, flag):
        self.flags |= flag
        if flag & self.FLAG.HIDDEN:
            self.hidden = True

    def remove_flag(self, flag):
        self.flags &= ~flag
        if flag & self.FLAG.HIDDEN:
            self.hidden = False

    def has_flag(self, flag):
        return bool(self.flags & flag)

    def add_state(self, state):
        self.state |= state

    def remove_state(self, state):
        self.state &= ~state

    def has_state(self, state):
        return bool(self.state & state)

    def set_scroll_dir(self, direction):
        self.scroll_dir = direction

    def get_scroll_y(self):
        return self.scroll_y

    def scroll_limit_y(self):
        """Tiles scroll to the bottom of their direct children."""
        if not hasattr(self, 'coord'):
            return 0
        bottom = self.height
        for child in self.children:
            if child.hidden:
                continue
            y = child.y
            if child.centered:
                y += (self.height - child.height) / 2
            bottom = max(bottom, y + child.height)
        return max(0, bottom - self.height)

    def scroll_to_y(self, y, anim=ANIM.OFF):
        # Animation is intentionally immediate in this simulator.
        self.scroll_y = max(0, min(y, self.scroll_limit_y()))

    def can_scroll_y(self, delta):
        direction = DIR.BOTTOM if delta > 0 else DIR.TOP
        return (self.has_flag(self.FLAG.SCROLLABLE)
                and bool(self.scroll_dir & direction)
                and self.scroll_limit_y() > 0)

    def add_event_cb(self, callback, event, data):
        self.events.append((callback, event, data))

    def send_event(self, code):
        for callback, event, data in self.events:
            if event in (EVENT.ALL, code):
                callback(SimpleNamespace(get_target=lambda: self,
                                         get_code=lambda: code,
                                         get_user_data=lambda d=data: d))

    def click(self):
        if not self.has_state(STATE.DISABLED):
            self.send_event(EVENT.CLICKED)

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


class switch(obj):
    """Boolean control with LVGL's checked-state and change-event interface."""

    def __init__(self, parent):
        super().__init__(parent)
        self.set_size(50, 28)
        self.add_flag(self.FLAG.CLICKABLE)
        self.remove_flag(self.FLAG.SCROLLABLE)

    def click(self):
        if self.has_state(STATE.DISABLED):
            return
        self.state ^= STATE.CHECKED
        self.send_event(EVENT.VALUE_CHANGED)
        self.send_event(EVENT.CLICKED)


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

    def set_tile(self, tile, anim=ANIM.OFF):
        if tile not in self.children:
            raise ValueError('Tile does not belong to this tileview')
        self.set_tile_by_index(*tile.coord, anim)

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
        # The canvas clips drawing at its edges. Clip hit targets as well,
        # so off-screen children cannot receive clicks after scrolling.
        bounds = (max(0, x), max(0, y),
                  min(_screen.width, x + node.width),
                  min(_screen.height, y + node.height))
        if node.bg:
            _canvas.create_rectangle(x, y, x + node.width, y + node.height,
                                     fill=node.bg, outline='')
        if isinstance(node, switch):
            disabled = node.has_state(STATE.DISABLED)
            track = ('#aaaaaa' if disabled else
                     '#2196f3' if node.has_state(STATE.CHECKED) else '#666666')
            radius = min(node.width, node.height) / 2
            _canvas.create_rectangle(x + radius, y, x + node.width - radius,
                                     y + node.height, fill=track, outline='')
            for left in (x, x + node.width - 2 * radius):
                _canvas.create_oval(left, y, left + 2 * radius,
                                    y + node.height, fill=track, outline='')
            diameter = max(0, min(node.width, node.height) - 6)
            knob_x = x + (node.width - diameter - 3
                          if node.has_state(STATE.CHECKED) else 3)
            _canvas.create_oval(knob_x, y + 3, knob_x + diameter,
                                y + 3 + diameter,
                                fill='#dddddd' if disabled else '#ffffff', outline='')
        if node.text is not None:
            _canvas.create_text(x, y, text=node.text, fill=node.fg,
                                font=('Arial', -node.font), anchor='center' if node.centered else 'nw')
        elif bounds[0] < bounds[2] and bounds[1] < bounds[3]:
            hits.append((*bounds, node))
        node.scroll_to_y(node.scroll_y)
        for child in node.children:
            if isinstance(node, tileview) and child.coord != node.active:
                continue
            draw(child, x, y - node.scroll_y)
    draw(_screen)
    return hits


def tileviews(node=None):
    node = node or _screen
    if isinstance(node, tileview):
        yield node
    for child in node.children:
        yield from tileviews(child)
