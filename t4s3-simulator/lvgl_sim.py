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
EVENT = SimpleNamespace(CLICKED=1, VALUE_CHANGED=2, FOCUSED=3, DEFOCUSED=4, READY=5, CANCEL=6, ALL=0)
STATE = SimpleNamespace(DEFAULT=0, CHECKED=1, DISABLED=2, FOCUSED=4)
PART = SimpleNamespace(MAIN=0, SELECTED=0x30000, ITEMS=0x20000, CURSOR=0x60000)
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
_focused_textarea = None
_refresh_pending = False
_refresh_callback = None
_refreshing = False


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
    if _refresh_pending:
        refr_now(None)
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
            and '\t' not in str(text)
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


def refr_now(display):
    """Flush the current canvas without running timers or application events."""
    global _refresh_pending, _refreshing
    if display is not None:
        raise NotImplementedError('The simulator supports one display; pass None to refr_now')
    if _canvas is None:
        raise RuntimeError('No simulated display is configured')
    if _refreshing:
        raise RuntimeError('The simulated display is already being refreshed')
    _refreshing = True
    _refresh_pending = False
    try:
        if _refresh_callback is not None:
            _refresh_callback()
        else:
            render()
        # Flush Tk drawing, without processing further input or timers.
        _canvas.update_idletasks()
    finally:
        _refreshing = False


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
        self._explicit_height = False
        self._ext_click_area = 0
        self.max_height = None

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
        self._explicit_height = True

    def set_width(self, width):
        self.width = width
        self._explicit_width = True

    def set_height(self, height):
        self.height = height
        self._explicit_height = True

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def update_layout(self):
        for child in self.children:
            child.update_layout()

    def invalidate(self):
        """Queue a redraw of this object's visible area, including its children."""
        global _refresh_pending
        ancestor = self
        while ancestor is not None:
            if ancestor.hidden:
                return
            if hasattr(ancestor, 'coord') and ancestor.coord != ancestor.parent.active:
                return
            if ancestor is _screen:
                _refresh_pending = True
                return
            ancestor = ancestor.parent

    def set_style_max_height(self, height, selector):
        if selector != PART.MAIN:
            raise NotImplementedError('Only MAIN max_height is supported')
        self.max_height = int(height)

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
            child.update_layout()
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
        global _focused_textarea
        self.clean()
        if self is _focused_textarea:
            _focused_textarea = None
        self._text_images.clear()
        if self.parent:
            self.parent.children.remove(self)

    def clean(self):
        """Delete all children while keeping the container itself."""
        for child in list(self.children):
            child.delete()


class label(obj):
    def __init__(self, parent):
        super().__init__(parent)
        self.text = ''
        self._measured_text = None

    def set_text(self, text):
        self.text = str(text)

    def get_text(self):
        return self.text

    def update_layout(self):
        width = self.width if self._explicit_width else None
        key = (self.text, font_signature(self.font), width)
        if self._measured_text is None or self._measured_text[0] != key:
            size = render_text(self.text, self.font, (0, 0, 0), width=width).size
            self._measured_text = key, size
        else:
            size = self._measured_text[1]
        if not self._explicit_width:
            self.width = size[0]
        if not self._explicit_height:
            self.height = size[1]

    def get_width(self):
        self.update_layout()
        return self.width

    def get_height(self):
        self.update_layout()
        return self.height


class textarea(obj):
    """Editable text with a Unicode character cursor and LVGL change events."""

    CURSOR_LAST = 0x7fff

    def __init__(self, parent):
        super().__init__(parent)
        self.set_size(200, 42)
        self.add_flag(self.FLAG.CLICKABLE)
        self.remove_flag(self.FLAG.SCROLLABLE)
        self._value = ''
        self.placeholder = ''
        self.cursor_pos = 0
        self.one_line = False
        self.max_length = 0
        self.accepted_chars = None

    def set_one_line(self, enabled):
        self.one_line = bool(enabled)
        if enabled:
            self.set_text(self._value)

    def set_placeholder_text(self, text):
        self.placeholder = str(text)

    def set_max_length(self, length):
        self.max_length = max(0, int(length))

    def set_accepted_chars(self, chars):
        self.accepted_chars = chars

    def _filter(self, text):
        return ''.join(char for char in str(text)
                       if (not self.one_line or char not in '\r\n')
                       and (self.accepted_chars is None or char in self.accepted_chars))

    def set_text(self, text):
        value = self._filter(text)
        if self.max_length:
            value = value[:self.max_length]
        changed = value != self._value
        self._value, self.cursor_pos = value, len(value)
        if changed:
            self.send_event(EVENT.VALUE_CHANGED)

    def get_text(self):
        return self._value

    def set_cursor_pos(self, position):
        position = int(position)
        if position < 0:
            position = len(self._value) + position
        self.cursor_pos = max(0, min(position, len(self._value)))

    def get_cursor_pos(self):
        return self.cursor_pos

    def add_text(self, text):
        text = self._filter(text)
        if self.max_length:
            text = text[:max(0, self.max_length - len(self._value))]
        if not text or self.has_state(STATE.DISABLED):
            return
        cursor = self.cursor_pos
        self._value = self._value[:cursor] + text + self._value[cursor:]
        self.cursor_pos += len(text)
        self.send_event(EVENT.VALUE_CHANGED)

    def add_char(self, char):
        self.add_text(chr(char) if isinstance(char, int) else char)

    def delete_char(self):
        if self.cursor_pos and not self.has_state(STATE.DISABLED):
            cursor = self.cursor_pos
            self._value = self._value[:cursor - 1] + self._value[cursor:]
            self.cursor_pos -= 1
            self.send_event(EVENT.VALUE_CHANGED)

    def delete_char_forward(self):
        if self.cursor_pos < len(self._value) and not self.has_state(STATE.DISABLED):
            cursor = self.cursor_pos
            self._value = self._value[:cursor] + self._value[cursor + 1:]
            self.send_event(EVENT.VALUE_CHANGED)

    def cursor_left(self):
        self.set_cursor_pos(max(0, self.cursor_pos - 1))

    def cursor_right(self):
        self.set_cursor_pos(self.cursor_pos + 1)

    def click(self):
        if not self.has_state(STATE.DISABLED):
            _focus_textarea(self)
            super().click()


def _focus_textarea(field):
    global _focused_textarea
    if field is _focused_textarea:
        return
    previous, _focused_textarea = _focused_textarea, field
    if previous:
        previous.remove_state(STATE.FOCUSED)
        previous.send_event(EVENT.DEFOCUSED)
    if field:
        field.add_state(STATE.FOCUSED)
        field.send_event(EVENT.FOCUSED)


def handle_key(key, char=''):
    """Return whether a focused, visible text area consumed desktop input."""
    field = _focused_textarea
    if field is None or field.has_state(STATE.DISABLED):
        return False
    ancestor = field
    while ancestor:
        if ancestor.hidden:
            return False
        if hasattr(ancestor, 'coord') and ancestor.coord != ancestor.parent.active:
            return False
        ancestor = ancestor.parent
    actions = {
        'BackSpace': field.delete_char, 'Delete': field.delete_char_forward,
        'Left': field.cursor_left, 'Right': field.cursor_right,
        'Home': lambda: field.set_cursor_pos(0),
        'End': lambda: field.set_cursor_pos(textarea.CURSOR_LAST),
        'Return': lambda: field.send_event(EVENT.READY) if field.one_line else field.add_text('\n'),
        'KP_Enter': lambda: field.send_event(EVENT.READY),
        'Escape': lambda: field.send_event(EVENT.CANCEL),
    }
    if key in actions:
        actions[key]()
    elif char and all(character.isprintable() for character in char):
        field.add_text(char)
    return True


class keyboard(obj):
    """Touch keyboard using the LVGL text-area binding and custom key maps."""

    MODE = SimpleNamespace(TEXT_LOWER=0, TEXT_UPPER=1, SPECIAL=2, NUMBER=3,
                           USER_1=4, USER_2=5, USER_3=6, USER_4=7)

    def __init__(self, parent):
        super().__init__(parent)
        self.set_size(600, 200)
        self.remove_flag(self.FLAG.SCROLLABLE)
        self.add_flag(self.FLAG.CLICKABLE)
        self.field = None
        self.mode = self.MODE.TEXT_UPPER
        self.maps = {}

    def set_textarea(self, field):
        if field is not None and not isinstance(field, textarea):
            raise TypeError('A keyboard must be bound to a textarea or None')
        if field is not None:
            _focus_textarea(field)
        elif self.field is _focused_textarea:
            _focus_textarea(None)
        self.field = field

    def get_textarea(self):
        return self.field

    def set_mode(self, mode):
        if mode not in vars(self.MODE).values():
            raise ValueError('Unknown keyboard mode')
        self.mode = mode
        self._text_images.clear()

    def get_mode(self):
        return self.mode

    def set_map(self, mode, key_map, controls):
        keys = list(key_map)
        count = len([key for key in keys if key not in ('', '\n')])
        if count != len(controls):
            raise ValueError('Keyboard controls must have one entry per key')
        self.maps[mode] = keys, list(controls)
        self._text_images.clear()

    def _rows(self):
        if self.mode in self.maps:
            keys, widths = self.maps[self.mode]
            rows, row, index = [], [], 0
            for key in keys:
                if not key:
                    break
                if key == '\n':
                    rows.append(row)
                    row = []
                else:
                    row.append((key, max(1, int(widths[index]) & 0xF)))
                    index += 1
            if row:
                rows.append(row)
            return [row for row in rows if row]
        if self.mode == self.MODE.NUMBER:
            rows = [list('123'), list('456'), list('789'), ['.', '0', SYMBOL.BACKSPACE]]
        elif self.mode == self.MODE.SPECIAL:
            rows = [list('1234567890'), list('+-*/=!?.,:;'), ['abc', SYMBOL.BACKSPACE]]
        else:
            upper = self.mode == self.MODE.TEXT_UPPER
            rows = [list(row.upper() if upper else row) for row in ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')]
            rows[-1] = ['abc' if upper else 'ABC'] + rows[-1] + [SYMBOL.BACKSPACE]
        rows.append(['1#' if self.mode not in (self.MODE.SPECIAL, self.MODE.NUMBER) else 'abc',
                     SYMBOL.CLOSE, SYMBOL.LEFT, ' ', SYMBOL.RIGHT, SYMBOL.OK])
        return [[(key, 4 if key == ' ' else 1) for key in row] for row in rows]

    def press_key(self, key):
        if self.has_state(STATE.DISABLED):
            return
        if key in ('ABC', 'abc', '1#'):
            self.set_mode({'ABC': self.MODE.TEXT_UPPER, 'abc': self.MODE.TEXT_LOWER,
                           '1#': self.MODE.SPECIAL}[key])
        elif key in (SYMBOL.OK, SYMBOL.CLOSE, SYMBOL.KEYBOARD):
            code = EVENT.READY if key == SYMBOL.OK else EVENT.CANCEL
            if self.field is not None:
                self.field.send_event(code)
            self.send_event(code)
        elif self.field is not None:
            if key == SYMBOL.BACKSPACE:
                self.field.delete_char()
            elif key == SYMBOL.LEFT:
                self.field.cursor_left()
            elif key == SYMBOL.RIGHT:
                self.field.cursor_right()
            elif key == SYMBOL.NEW_LINE:
                if self.field.one_line:
                    self.field.send_event(EVENT.READY)
                else:
                    self.field.add_text('\n')
            else:
                self.field.add_text(key)

    def delete(self):
        self.set_textarea(None)
        super().delete()


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
    """Scrollable popup kept outside the normal child drawing tree."""

    def __init__(self, owner):
        super().__init__()
        self.parent = owner
        self.selected_colors = {}
        self.row_height = 28
        self.reveal_selected = False

    def scroll_limit_y(self):
        return max(0, len(self.parent.options) * self.row_height - self.height)

    def layout(self, x, y):
        """Fit whole rows above or below the control, within the display."""
        owner = self.parent
        self.row_height = max(28, _font_size(self.font) + 12)
        below = max(0, _screen.height - (y + owner.height))
        above = max(0, y)
        content_height = len(owner.options) * self.row_height
        opens_above = content_height > below and above > below
        available = above if opens_above else below
        if self.max_height is not None:
            available = min(available, self.max_height)
        rows = min(len(owner.options), max(1, int(available // self.row_height)))
        self.width = min(owner.width, _screen.width)
        self.height = rows * self.row_height
        self.x = max(0, min(x, _screen.width - self.width))
        top = y - self.height if opens_above else y + owner.height
        self.y = max(0, min(top, _screen.height - self.height))
        if self.reveal_selected:
            self.scroll_to_y((owner.selected - rows // 2) * self.row_height)
            self.reveal_selected = False
        else:
            self.scroll_to_y(self.scroll_y)

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
        self.popup.scroll_y = 0
        self.popup._text_images.clear()
        self.close()

    def get_options(self):
        return '\n'.join(self.options)

    def get_option_count(self):
        return len(self.options)

    def set_selected(self, index):
        if self.options:
            self.selected = max(0, min(int(index), len(self.options) - 1))
            if self.opened:
                self.popup.reveal_selected = True

    def get_selected(self):
        return self.selected

    def open(self):
        if not self.has_state(STATE.DISABLED) and self.options:
            if not self.opened:
                self.popup.reveal_selected = True
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


def setup(canvas, on_refresh=None):
    global _canvas, _screen, _focused_textarea, _refresh_pending, _refresh_callback
    _canvas = canvas
    _focused_textarea = None
    _refresh_pending = False
    _refresh_callback = on_refresh
    _screen = obj()
    _screen.set_size(600, 450)
    _screen.bg = '#ffffff'
    return _screen


def teardown(canvas):
    """Detach a closed simulator without disturbing another active canvas."""
    global _canvas, _screen, _focused_textarea, _refresh_pending, _refresh_callback
    if _canvas is canvas:
        _canvas = _screen = _focused_textarea = _refresh_callback = None
        _refresh_pending = False


def render():
    global _refresh_pending
    _refresh_pending = False
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
        if isinstance(node, textarea):
            _canvas.create_rectangle(x, y, x + node.width, y + node.height,
                                     fill=node.bg or '#ffffff',
                                     outline='#2196f3' if node.has_state(STATE.FOCUSED) else '#888888')
            value = node.get_text()
            start = 0
            available = max(1, node.width - 20)
            def text_width(text):
                return render_text(text, node.font, (0, 0, 0)).width if text else 0
            if node.one_line:
                while start < node.cursor_pos and text_width(value[start:node.cursor_pos]) > available:
                    start += 1
            caption = value[start:] if value else node.placeholder
            while caption and text_width(caption) > available:
                caption = caption[:-1]
            _draw_text(node, x + 8, y + node.height / 2, caption,
                       node.fg if value else '#888888', node.font, anchor='w')
            if node.has_state(STATE.FOCUSED):
                cursor_x = x + 8 + text_width(value[start:node.cursor_pos])
                _canvas.create_line(cursor_x, y + 8, cursor_x, y + node.height - 8,
                                    fill=node.fg, width=1)
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
        if isinstance(node, keyboard):
            rows = node._rows()
            row_height = node.height / max(1, len(rows))
            for row_index, row in enumerate(rows):
                total_width = sum(weight for _key, weight in row)
                offset = 0
                for key_index, (key, weight) in enumerate(row):
                    left = x + node.width * offset / total_width + 2
                    right = x + node.width * (offset + weight) / total_width - 2
                    top = y + row_index * row_height + 2
                    bottom = y + (row_index + 1) * row_height - 2
                    offset += weight
                    _canvas.create_rectangle(left, top, right, bottom,
                                             fill=node.bg or '#e0e5eb', outline='#888888')
                    _draw_text(node, (left + right) / 2, (top + bottom) / 2,
                               'Space' if key == ' ' else key,
                               '#888888' if node.has_state(STATE.DISABLED) else node.fg,
                               node.font, anchor='center', slot=f'key{row_index}_{key_index}')
                    touch = obj()
                    touch.parent = node
                    touch.add_flag(obj.FLAG.CLICKABLE)
                    touch.click = lambda k=key, owner=node: owner.press_key(k)
                    add_hit(touch, (left, top, right, bottom), bounds)
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
        popup = node.get_list()
        popup.layout(x, y)
        left, top = popup.x, popup.y
        right, bottom = left + popup.width, top + popup.height
        row_height = popup.row_height
        hits.append((left, top, right, bottom, popup))
        background = popup.bg or node.bg or '#eeeeee'
        # Keep text and touch targets on complete rows. Pixel offsets accumulate
        # for small trackpad deltas; the visible list advances one row at a time.
        first = int(popup.scroll_y // row_height)
        last = min(len(node.options), first + int(popup.height // row_height))
        visible_slots = {f'row{index}' for index in range(first, last)}
        for slot in list(popup._text_images):
            if slot not in visible_slots:
                del popup._text_images[slot]
        scrolling = popup.scroll_limit_y() > 0
        for index in range(first, last):
            row_y = top + (index - first) * row_height
            selected = index == node.selected
            _canvas.create_rectangle(left, row_y, right, row_y + row_height,
                                     fill=popup.selected_color('bg', '#476582') if selected else background,
                                     outline='#888888')
            _draw_text(popup, left + 8, row_y + row_height / 2, node.options[index],
                       popup.selected_color('fg', '#ffffff') if selected else popup.fg,
                       popup.font, anchor='w', width=max(1, popup.width - (24 if scrolling else 16)),
                       slot=f'row{index}')
            choice = obj()
            choice.parent = popup
            choice.add_flag(obj.FLAG.CLICKABLE)
            choice.click = lambda n=node, i=index: n.select(i)
            hits.append((left, row_y, right, row_y + row_height, choice))
        if scrolling:
            thumb_height = max(16, popup.height * popup.height / (len(node.options) * row_height))
            thumb_top = top + (popup.height - thumb_height) * popup.scroll_y / popup.scroll_limit_y()
            _canvas.create_rectangle(right - 7, top + 2, right - 2, bottom - 2,
                                     fill='#888888', outline='')
            _canvas.create_rectangle(right - 7, thumb_top, right - 2, thumb_top + thumb_height,
                                     fill=popup.fg, outline='')
    return hits


def tileviews(node=None):
    node = node or _screen
    if isinstance(node, tileview):
        yield node
    for child in node.children:
        yield from tileviews(child)
