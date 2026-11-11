"""Explicit, small LVGL compatibility layer rendered by Tk, not native LVGL."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace

from PIL import Image
from font_sim import BinaryFont, BuiltinFont, font_signature, render_text, resolve_glyph
from timer_sim import NO_TIMER_READY, Timer as timer_t, TimerManager

OPA = SimpleNamespace(COVER=255, TRANSP=0)
DIR = SimpleNamespace(NONE=0, LEFT=1, RIGHT=2, TOP=4, BOTTOM=8, HOR=3, VER=12, ALL=15)
EVENT = SimpleNamespace(CLICKED=1, VALUE_CHANGED=2, ALL=0)
STATE = SimpleNamespace(DEFAULT=0, CHECKED=1, DISABLED=2)
PART = SimpleNamespace(MAIN=0, SELECTED=0x30000)
ANIM = SimpleNamespace(OFF=0, ON=1)
SCROLLBAR_MODE = SimpleNamespace(OFF=0)
ALIGN = SimpleNamespace(CENTER=0, TOP_LEFT=1, TOP_MID=2, BOTTOM_MID=3)
SYMBOL = SimpleNamespace(**json.loads(
    (Path(__file__).with_name('fonts') / 'symbols.json').read_text(encoding='utf-8')))
for _font_size in range(12, 50, 2):
    globals()[f'font_montserrat_{_font_size}'] = BuiltinFont(_font_size)
FONT_DEFAULT = font_montserrat_16
_screen = None
_canvas = None
_filesystem_root = None
_filesystem_drivers = {}
_timer_manager = TimerManager()


@contextmanager
def timer_context():
    """Cancel application timers when a simulated run ends."""
    global _timer_manager
    previous = _timer_manager
    _timer_manager = TimerManager()
    try:
        yield
    finally:
        _timer_manager.clear()
        _timer_manager = previous


def timer_create(callback, period, user_data=None):
    return _timer_manager.create(callback, period, user_data)


def timer_create_basic():
    return timer_create(None, 500, None)


def timer_handler():
    if _timer_manager.running:
        return 1
    _timer_manager.run_due()
    return _timer_manager.next_delay()


def timer_enable(enabled):
    _timer_manager.enabled = bool(enabled)


def timer_get_time_until_next():
    return _timer_manager.next_delay()


# Expose the LVGL function spellings as well as timer.pause(), reset(), etc.
timer_delete = timer_t.delete
timer_del = timer_delete  # LVGL 8 name.
timer_pause = timer_t.pause
timer_resume = timer_t.resume
timer_ready = timer_t.ready
timer_reset = timer_t.reset
timer_set_period = timer_t.set_period
timer_get_period = timer_t.get_period
timer_set_cb = timer_t.set_cb
timer_set_user_data = timer_t.set_user_data
timer_get_user_data = timer_t.get_user_data
timer_get_paused = timer_t.get_paused
timer_set_repeat_count = timer_t.set_repeat_count
timer_set_auto_delete = timer_t.set_auto_delete


@contextmanager
def filesystem(root):
    """Keep LVGL drive registrations local to one simulated device run."""
    global _filesystem_root, _filesystem_drivers
    previous_root, previous_drivers = _filesystem_root, _filesystem_drivers
    builtin_fallbacks = [(font, font.fallback) for font in globals().values() if isinstance(font, BuiltinFont)]
    for font, _ in builtin_fallbacks:
        font.fallback = None
    _filesystem_root, _filesystem_drivers = Path(root).resolve(), {}
    try:
        yield
    finally:
        _filesystem_root, _filesystem_drivers = previous_root, previous_drivers
        for font, fallback in builtin_fallbacks:
            font.fallback = fallback


class fs_drv_t:
    """Registration information for a drive backed by the simulated VFS."""

    def __init__(self):
        self.init()

    def init(self):
        self.letter = 0
        self.cache_size = 0

    def register(self):
        letter = chr(self.letter)
        if not letter.isascii() or not letter.isalpha():
            raise ValueError('LVGL filesystem drive must be one ASCII letter')
        self.root = _filesystem_root or Path.cwd().resolve()
        _filesystem_drivers[letter] = self


def _filesystem_path(source, kind):
    """Resolve an LVGL filename inside its registered virtual filesystem."""
    if not isinstance(source, str) or len(source) < 2 or source[1] != ':':
        raise ValueError(f'{kind} sources must use a registered LVGL drive, e.g. S:/assets/file')
    driver = _filesystem_drivers.get(source[0])
    if driver is None:
        raise ValueError(f'LVGL filesystem drive {source[0]} is not registered')
    path = (driver.root / source[2:].lstrip('/\\')).resolve()
    if not path.is_relative_to(driver.root):
        raise ValueError(f'{kind} source is outside the simulated filesystem')
    if not path.is_file():
        raise FileNotFoundError(f'{kind} is missing from the filesystem image: {source}')
    return path


def image_path(source):
    """Resolve a PNG filename such as S:/assets/qr.png inside its VFS."""
    return _filesystem_path(source, 'Image')


def color_hex(value):
    return '#%06x' % value


def font_text(text, font):
    if not isinstance(font, BuiltinFont):
        return text
    return ''.join(char if char in '\n\r\t' or resolve_glyph(font, ord(char))[1] is not None
                   else '□' for char in text)


def binfont_create(source):
    """Load glyphs from the same registered drive paths as the device."""
    return BinaryFont(_filesystem_path(source, 'Font').read_bytes(), source)


def binfont_create_from_buffer(buffer, size=None):
    data = bytes(buffer)
    if size is not None:
        if not 0 <= size <= len(data):
            raise ValueError('Invalid binary font buffer size')
        data = data[:size]
    return BinaryFont(data)


def binfont_destroy(font):
    if font is not None:
        if not isinstance(font, BinaryFont):
            raise TypeError('Only allocated binary fonts can be destroyed')
        font.destroy()


# LVGL 8 spellings, retained alongside the firmware's LVGL 9 API.
font_load = binfont_create
font_free = binfont_destroy


def _draw_text(node, x, y, text, color, font, anchor='nw', width=None, slot='text'):
    # Retain the existing Tk preview for ordinary built-in text. Custom fonts,
    # fallbacks, and symbols use their actual bitmap data, never OS substitutes.
    if (isinstance(font, BuiltinFont) and font.fallback is None
            and all(ord(char) < 0xF000 for char in str(text))):
        options = {'width': width} if width is not None else {}
        return _canvas.create_text(x, y, text=font_text(text, font), fill=color,
                                   font=('Arial', -int(font)), anchor=anchor, **options)
    key = (str(text), color, font_signature(font), width)
    cached = node._text_images.get(slot)
    if cached is None or cached[0] != key:
        rgb = tuple(channel // 257 for channel in _canvas.winfo_rgb(color))
        pixels = render_text(text, font, rgb, width)
        stream = BytesIO()
        pixels.save(stream, format='PNG')
        photo = tk.PhotoImage(master=_canvas, data=stream.getvalue(), format='png')
        node._text_images[slot] = key, photo
    else:
        photo = cached[1]
    return _canvas.create_image(x, y, image=photo, anchor=anchor)


def _font_size(font):
    return int(font) if isinstance(font, int) else font.size


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
        self.bg, self._fg, self._font = None, None, None
        self.border_width, self.border_color = 0, '#000000'
        self.centered = False
        self.hidden = False
        self.flags = self.FLAG.SCROLLABLE
        self.state = STATE.DEFAULT
        self.scroll_y = 0
        self.scroll_dir = DIR.ALL
        self.events = []
        self.text = None
        self._text_images = {}
        self._explicit_width = False
        self._ext_click_area = 0

    @property
    def fg(self):
        if self._fg is not None:
            return self._fg
        return self.parent.fg if self.parent else '#000000'

    @fg.setter
    def fg(self, color):
        self._fg = color

    @property
    def font(self):
        return self._font if self._font is not None else (
            self.parent.font if self.parent else font_montserrat_16)

    @font.setter
    def font(self, font):
        self._font = font

    def set_size(self, width, height):
        self.width, self.height = width, height
        self._explicit_width = True

    def set_width(self, width):
        self.width = width
        self._explicit_width = True

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
        if selector != PART.MAIN:
            raise NotImplementedError('Only borders on the default selector are supported')
        self.border_width = max(0, int(width))

    def set_style_border_color(self, color, selector):
        if selector != PART.MAIN:
            raise NotImplementedError('Only borders on the default selector are supported')
        self.border_color = color

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

    def set_ext_click_area(self, size):
        """Extend touch bounds on all sides without changing the drawing."""
        self._ext_click_area = max(0, int(size))

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

    def send_event(self, code, param=None):
        for callback, event, data in list(self.events):
            if event in (EVENT.ALL, code):
                callback(SimpleNamespace(get_target=lambda: self,
                                         get_target_obj=lambda: self,
                                         get_current_target=lambda: self,
                                         get_current_target_obj=lambda: self,
                                         get_code=lambda: code,
                                         get_param=lambda: param,
                                         get_user_data=lambda d=data: d))

    def click(self):
        if not self.has_state(STATE.DISABLED):
            self.send_event(EVENT.CLICKED)

    def delete(self):
        self._text_images.clear()
        if self.parent:
            self.parent.children.remove(self)

    def clean(self):
        """Delete all children while keeping the container itself."""
        for child in list(self.children):
            child.clean()
            child.delete()


class label(obj):
    def __init__(self, parent):
        super().__init__(parent)
        self.text = ''

    def set_text(self, text):
        self.text = str(text)

    def get_text(self):
        return self.text


class image(obj):
    """A native-size PNG or text/symbol image using the selected font."""

    def __init__(self, parent):
        super().__init__(parent)
        self.set_size(0, 0)
        self.remove_flag(self.FLAG.SCROLLABLE)
        self._source = None
        self._photo = None
        self._pixels = None
        self._recolor = (0, 0, 0)
        self._recolor_opa = OPA.TRANSP
        self._rendered_style = None
        self._symbol_text = None
        self._symbol_size_key = None

    def set_src(self, source):
        if source is None:
            self._source = self._photo = self._pixels = None
            self._rendered_style = None
            self._symbol_text = None
            self._text_images.clear()
            self.set_size(0, 0)
            return
        if source == self._source and self._photo is not None:
            return
        if isinstance(source, str) and source and ord(source[0]) >= 0x80:
            self._source = source
            self._symbol_text = source.removeprefix(SYMBOL.DUMMY)
            self._photo = self._pixels = None
            self._rendered_style = self._symbol_size_key = None
            self._text_images.clear()
            self._update_symbol_size()
            return
        path = image_path(source)
        with Image.open(path, formats=['PNG']) as loaded:
            pixels = loaded.convert('RGBA')
        self._source, self._pixels = source, pixels
        self._symbol_text = None
        self._text_images.clear()
        self._rendered_style = None
        self.set_size(*pixels.size)
        self._update_photo()

    def _update_symbol_size(self):
        if self._symbol_text is None:
            return
        key = self._symbol_text, font_signature(self.font)
        if key != self._symbol_size_key:
            pixels = render_text(self._symbol_text, self.font, '#ffffff')
            self.set_size(*pixels.size)
            self._symbol_size_key = key

    def set_style_image_recolor(self, color, selector):
        if selector != PART.MAIN:
            raise NotImplementedError('Only image recoloring on the default selector is supported')
        # Use Tk's color parser, matching the simulator's other color styles.
        rgb = tuple(channel // 257 for channel in _canvas.winfo_rgb(color))
        self._recolor = rgb
        self._update_photo()

    def set_style_image_recolor_opa(self, opacity, selector):
        if selector != PART.MAIN:
            raise NotImplementedError('Only image recoloring on the default selector is supported')
        if not isinstance(opacity, int) or not 0 <= opacity <= 255:
            raise ValueError('Image recolor opacity must be an integer from 0 to 255')
        self._recolor_opa = opacity
        self._update_photo()

    def _update_photo(self):
        if self._pixels is None:
            return
        style = (self._recolor if self._recolor_opa else None, self._recolor_opa)
        if style == self._rendered_style:
            return
        pixels = self._pixels
        if self._recolor_opa:
            tint = Image.new('RGBA', pixels.size, self._recolor)
            pixels = Image.blend(pixels, tint, self._recolor_opa / 255)
            pixels.putalpha(self._pixels.getchannel('A'))
        encoded = BytesIO()
        pixels.save(encoded, format='PNG')
        self._photo = tk.PhotoImage(master=_canvas, data=encoded.getvalue(), format='png')
        self._rendered_style = style

    def get_src(self):
        return self._source

    def delete(self):
        super().delete()
        self._photo = self._pixels = None
        self._rendered_style = None


class button(obj):
    def __init__(self, parent):
        super().__init__(parent)
        self.add_flag(self.FLAG.CLICKABLE)
        self.bg = '#dddddd'


btn = button


class _DropdownList(obj):
    """Popup styles kept outside the normal child drawing tree."""

    def __init__(self, owner):
        super().__init__()
        self.parent = owner
        self.selected_colors = {}

    def _set_color(self, name, color, selector):
        if selector == PART.MAIN:
            setattr(self, name, color)
        elif selector in (PART.SELECTED, PART.SELECTED | STATE.CHECKED):
            self.selected_colors[(name, selector)] = color
        else:
            raise NotImplementedError('Dropdown list colors support MAIN and SELECTED (optionally CHECKED)')

    def set_style_bg_color(self, color, selector):
        self._set_color('bg', color, selector)

    def set_style_text_color(self, color, selector):
        self._set_color('fg', color, selector)

    def selected_color(self, name, fallback):
        return self.selected_colors.get(
            (name, PART.SELECTED | STATE.CHECKED),
            self.selected_colors.get((name, PART.SELECTED), fallback))


class dropdown(obj):
    """Single-choice dropdown with newline-separated options."""

    def __init__(self, parent):
        super().__init__(parent)
        self.set_size(160, 40)
        self.add_flag(self.FLAG.CLICKABLE)
        self.remove_flag(self.FLAG.SCROLLABLE)
        self.options = ['Option 1', 'Option 2', 'Option 3']
        self.selected = 0
        self.opened = False
        self.popup = _DropdownList(self)

    def get_list(self):
        return self.popup

    def set_options(self, options):
        self.options = str(options).split('\n') if options else []
        self.selected = 0
        self.close()

    def get_options(self):
        return '\n'.join(self.options)

    def get_option_count(self):
        return len(self.options)

    def set_selected(self, index):
        if self.options:
            self.selected = max(0, min(int(index), len(self.options) - 1))

    def get_selected(self):
        return self.selected

    def open(self):
        if not self.has_state(STATE.DISABLED) and self.options:
            self.opened = True

    def close(self):
        self.opened = False

    def is_open(self):
        return self.opened

    def click(self):
        if self.has_state(STATE.DISABLED):
            return
        if self.opened:
            self.close()
        else:
            self.open()
        self.send_event(EVENT.CLICKED)

    def select(self, index):
        if self.has_state(STATE.DISABLED):
            return
        previous = self.selected
        self.set_selected(index)
        self.close()
        if self.selected != previous:
            self.send_event(EVENT.VALUE_CHANGED)


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
        if self.active != (col, row):
            self.active = (col, row)
            self.send_event(EVENT.VALUE_CHANGED)

    def get_tile_active(self):
        return next((tile for tile in self.children if tile.coord == self.active), None)

    def set_tile(self, tile, anim=ANIM.OFF):
        if tile not in self.children:
            raise ValueError('Tile does not belong to this tileview')
        self.set_tile_by_index(*tile.coord, anim)

    def move(self, dx, dy):
        direction = DIR.RIGHT if dx > 0 else DIR.LEFT if dx < 0 else DIR.BOTTOM if dy > 0 else DIR.TOP
        current = next(t for t in self.children if t.coord == self.active)
        target = (self.active[0] + dx, self.active[1] + dy)
        if current.directions & direction and target in [t.coord for t in self.children]:
            self.set_tile_by_index(*target)


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
    dropdowns = []

    def intersect(area, clip):
        return (max(area[0], clip[0]), max(area[1], clip[1]),
                min(area[2], clip[2]), min(area[3], clip[3]))

    def add_hit(node, area, clip):
        padding = node._ext_click_area if node.has_flag(obj.FLAG.CLICKABLE) else 0
        left, top, right, bottom = area
        bounds = intersect((left - padding, top - padding,
                            right + padding, bottom + padding), clip)
        if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
            hits.append((*bounds, node))

    def draw(node, px=0, py=0, clip=None):
        if node.hidden:
            return
        if clip is None:
            clip = (0, 0, _screen.width, _screen.height)
        if isinstance(node, image):
            node._update_symbol_size()
        x, y = px + node.x, py + node.y
        if node.centered and node.parent:
            x += node.parent.width / 2
            y += node.parent.height / 2
            if node.text is None:
                x -= node.width / 2
                y -= node.height / 2
        # Extended touch areas stay within the parent's bounds, as on LVGL.
        # Use the unexpanded bounds to clip children and popup visibility.
        bounds = intersect((x, y, x + node.width, y + node.height), clip)
        if node.bg:
            _canvas.create_rectangle(x, y, x + node.width, y + node.height,
                                     fill=node.bg, outline='')
        if isinstance(node, image):
            if node._symbol_text is not None:
                _draw_text(node, x, y, node._symbol_text, node.fg, node.font, slot='symbol')
            elif node._photo is not None:
                _canvas.create_image(x, y, image=node._photo, anchor='nw')
        if isinstance(node, dropdown):
            _canvas.create_rectangle(x, y, x + node.width, y + node.height,
                                     fill=node.bg or '#eeeeee', outline='#888888')
            caption = node.options[node.selected] if node.options else ''
            _draw_text(node, x + 8, y + node.height / 2, caption,
                       '#888888' if node.has_state(STATE.DISABLED) else node.fg,
                       node.font, anchor='w', width=max(1, node.width - 32), slot='caption')
            _canvas.create_text(x + node.width - 14, y + node.height / 2,
                                text='▾', fill=node.fg, anchor='center')
            if node.opened and not node.has_state(STATE.DISABLED) and bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                dropdowns.append((node, x, y))
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
            text_item = _draw_text(
                node, x, y, node.text, node.fg, node.font,
                anchor='center' if node.centered else 'nw',
                width=node.width if node._explicit_width else None)
            if node.has_flag(obj.FLAG.CLICKABLE):
                # Labels use content sizing on the device. Match the visible
                # text here, including centered text and long link captions.
                text_bounds = _canvas.bbox(text_item)
                if text_bounds:
                    add_hit(node, text_bounds, clip)
        else:
            add_hit(node, (x, y, x + node.width, y + node.height), clip)
        node.scroll_to_y(node.scroll_y)
        for child in node.children:
            if isinstance(node, tileview) and child.coord != node.active:
                continue
            draw(child, x, y - node.scroll_y, bounds)
        if node.border_width:
            width = min(node.border_width, node.width, node.height)
            inset = width / 2
            _canvas.create_rectangle(x + inset, y + inset,
                                     x + node.width - inset, y + node.height - inset,
                                     fill='', outline=node.border_color, width=width)
    draw(_screen)
    # Draw the popup last so it receives clicks ahead of underlying widgets.
    for node, x, y in dropdowns:
        blocker = obj()
        blocker.add_flag(obj.FLAG.CLICKABLE)
        blocker.click = node.close
        hits.append((0, 0, _screen.width, _screen.height, blocker))
        row_height = max(28, _font_size(node.font) + 12)
        popup_height = row_height * len(node.options)
        left = max(0, min(x, _screen.width - node.width))
        top = y + node.height
        if top + popup_height > _screen.height:
            top = max(0, y - popup_height)
        popup = node.get_list()
        background = popup.bg or node.bg or '#eeeeee'
        for index, option in enumerate(node.options):
            row_y = top + index * row_height
            selected = index == node.selected
            _canvas.create_rectangle(left, row_y, left + node.width, row_y + row_height,
                                     fill=popup.selected_color('bg', '#476582') if selected else background,
                                     outline='#888888')
            _draw_text(popup, left + 8, row_y + row_height / 2, option,
                       popup.selected_color('fg', '#ffffff') if selected else popup.fg,
                       popup.font, anchor='w', width=max(1, node.width - 16), slot=f'row{index}')
            choice = obj()
            choice.add_flag(obj.FLAG.CLICKABLE)
            choice.click = lambda n=node, i=index: n.select(i)
            if row_y < _screen.height:
                hits.append((left, row_y, min(_screen.width, left + node.width),
                             min(_screen.height, row_y + row_height), choice))
    return hits


def tileviews(node=None):
    node = node or _screen
    if isinstance(node, tileview):
        yield node
    for child in node.children:
        yield from tileviews(child)
