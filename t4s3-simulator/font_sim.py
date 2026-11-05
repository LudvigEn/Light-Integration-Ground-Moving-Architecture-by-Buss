"""LVGL binary bitmap fonts, independent of Tk and the simulated filesystem.

Format reference: https://github.com/lvgl/lv_font_conv/blob/master/doc/font_spec.md
Supports packed and RLE-compressed glyphs, character maps, and both kerning tables.
"""
from dataclasses import dataclass
import math
from pathlib import Path
import re
import struct

from PIL import Image, ImageChops, ImageDraw


class _Bits:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, count, signed=False):
        if not 0 <= count <= 32 or self.position + count > len(self.data) * 8:
            raise ValueError('Truncated or invalid binary font glyph')
        result = 0
        for _ in range(count):
            result = (result << 1) | ((self.data[self.position // 8] >> (7 - self.position % 8)) & 1)
            self.position += 1
        if signed and count and result & (1 << (count - 1)):
            result -= 1 << count
        return result


@dataclass
class Glyph:
    advance: float
    x: int
    y: int
    mask: Image.Image


class BinaryFont:
    """An allocated LVGL font; glyph bitmaps are decoded on demand."""

    def __init__(self, data, source='<buffer>'):
        self.source = str(source)
        self.fallback = None
        self.destroyed = False
        self._glyphs = {}
        self._pairs = {}
        self._classes = None
        try:
            self._load(bytes(data))
        except (IndexError, struct.error, KeyError) as error:
            raise ValueError(f'Invalid binary font: {self.source}') from error

    def _load(self, data):
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('Binary font is too large')
        tables, offset = {}, 0
        while offset < len(data):
            length, tag = struct.unpack_from('<I4s', data, offset)
            if length < 8 or offset + length > len(data) or tag in tables:
                raise ValueError('Invalid binary font table boundaries')
            tables[tag] = data[offset:offset + length]
            offset += length
        head = tables[b'head']
        if len(head) < 48 or struct.unpack_from('<I', head, 8)[0] != 1:
            raise ValueError('Unsupported binary font header')
        self.size, self.ascent, descent = struct.unpack_from('<HHh', head, 14)
        self.line_height, self.base_line = self.ascent - descent, -descent
        if not 0 < self.line_height <= 4096:
            raise ValueError('Invalid binary font line height')
        self._default_advance, scale = struct.unpack_from('<HH', head, 30)
        loc_format, self._id_format, self._advance_format = head[34:37]
        self.bpp, self._xy_bits, self._wh_bits, self._advance_bits, self.compression = head[37:42]
        if self.bpp not in (1, 2, 3, 4, 8) or self.compression not in (0, 1, 2):
            raise ValueError('Unsupported binary font bitmap format')
        if head[42]:
            raise NotImplementedError('Subpixel binary fonts are not supported by the simulator')
        if loc_format not in (0, 1) or self._id_format not in (0, 1) or self._advance_format not in (0, 1):
            raise ValueError('Unsupported binary font index format')
        self.underline_position, self.underline_thickness = struct.unpack_from('<hH', head, 44)
        self._kern_scale = scale / 256  # FP4.4 value multiplied by FP12.4 scale.
        self._glyf = tables[b'glyf']
        loca = tables[b'loca']
        count = struct.unpack_from('<I', loca, 8)[0]
        if not 1 <= count <= 65536:
            raise ValueError('Invalid binary font glyph count')
        self._offsets = struct.unpack_from('<' + ('I' if loc_format else 'H') * count, loca, 12)
        if any(start < 8 or start > len(self._glyf) for start in self._offsets):
            raise ValueError('Invalid binary font glyph location')
        if tuple(sorted(self._offsets)) != self._offsets:
            raise ValueError('Unordered binary font glyph locations')
        self.cmap = self._load_cmap(tables[b'cmap'])
        if any(not 0 < gid < count for gid in self.cmap.values()):
            raise ValueError('Character map references a missing glyph')
        self._load_kerning(tables.get(b'kern'))

    @staticmethod
    def _load_cmap(data):
        mapping = {}
        count = struct.unpack_from('<I', data, 8)[0]
        if count > (len(data) - 12) // 16:
            raise ValueError('Invalid binary font character map count')
        for index in range(count):
            start, first, span, gid, total, kind = struct.unpack_from('<IIHHHB', data, 12 + index * 16)
            if first + span > 0x110000:
                raise ValueError('Character map exceeds Unicode range')
            if kind == 2:
                mapping.update((first + delta, gid + delta) for delta in range(span))
            elif kind == 0:
                if start + span > len(data):
                    raise ValueError('Truncated binary font character map')
                mapping.update((first + delta, gid + data[start + delta])
                               for delta in range(span) if delta == 0 or data[start + delta])
            elif kind in (1, 3):
                codes = struct.unpack_from('<' + 'H' * total, data, start)
                ids = (range(total) if kind == 3 else
                       struct.unpack_from('<' + 'H' * total, data, start + total * 2))
                if any(code >= span for code in codes):
                    raise ValueError('Invalid sparse character map')
                mapping.update((first + code, gid + delta) for code, delta in zip(codes, ids))
            else:
                raise ValueError('Unsupported binary font character map')
        return mapping

    def _load_kerning(self, data):
        if data is None:
            return
        if data[8] == 0:
            count = struct.unpack_from('<I', data, 12)[0]
            width = 2 if self._id_format else 1
            if 16 + count * (2 * width + 1) > len(data):
                raise ValueError('Truncated binary font kerning pairs')
            ids = struct.unpack_from('<' + ('H' if width == 2 else 'B') * count * 2, data, 16)
            values = struct.unpack_from('<' + 'b' * count, data, 16 + count * width * 2)
            self._pairs = {(ids[2*i], ids[2*i+1]): value for i, value in enumerate(values)}
        elif data[8] == 3:
            count, left_count, right_count = struct.unpack_from('<HBB', data, 12)
            end = 16 + 2 * count + left_count * right_count
            if end > len(data):
                raise ValueError('Truncated binary font kerning classes')
            left = data[16:16 + count]
            right = data[16 + count:16 + 2 * count]
            if any(value > left_count for value in left) or any(value > right_count for value in right):
                raise ValueError('Invalid binary font kerning class')
            values = struct.unpack_from('<' + 'b' * (left_count * right_count), data, 16 + 2 * count)
            self._classes = left, right, right_count, values
        else:
            raise ValueError('Unsupported binary font kerning table')

    def kerning(self, left, right):
        self._check_alive()
        first, second = self.cmap.get(left), self.cmap.get(right)
        if first is None or second is None:
            return 0
        if self._classes:
            left_map, right_map, columns, values = self._classes
            a = left_map[first] if first < len(left_map) else 0
            b = right_map[second] if second < len(right_map) else 0
            value = values[(a - 1) * columns + b - 1] if a and b else 0
        else:
            value = self._pairs.get((first, second), 0)
        return value * self._kern_scale

    def _check_alive(self):
        if self.destroyed:
            raise ValueError('Binary font has been destroyed')

    def glyph(self, code):
        self._check_alive()
        if code not in self.cmap:
            return None
        if code in self._glyphs:
            return self._glyphs[code]
        gid = self.cmap[code]
        start = self._offsets[gid]
        end = self._offsets[gid + 1] if gid + 1 < len(self._offsets) else len(self._glyf)
        bits = _Bits(self._glyf[start:end])
        advance = bits.read(self._advance_bits) if self._advance_bits else self._default_advance
        if self._advance_format:
            advance /= 16
        x, y = bits.read(self._xy_bits, True), bits.read(self._xy_bits, True)
        width, height = bits.read(self._wh_bits), bits.read(self._wh_bits)
        if width * height > 4 * 1024 * 1024:
            raise ValueError('Binary font glyph is too large')
        pixels = self._decode_pixels(bits, width, height)
        mask = Image.new('L', (width, height))
        if pixels:
            maximum = (1 << self.bpp) - 1
            mask.putdata([round(value * 255 / maximum) for value in pixels])
        result = Glyph(advance, x, y, mask)
        self._glyphs[code] = result
        return result

    def _decode_pixels(self, bits, width, height):
        count = width * height
        if self.compression == 0:
            return [bits.read(self.bpp) for _ in range(count)]
        pixels, previous = [], None
        while len(pixels) < count:
            value = bits.read(self.bpp)
            pixels.append(value)
            if value == previous:
                repeats = 0
                while repeats < 11 and bits.read(1):
                    repeats += 1
                if repeats == 11:
                    repeats = 10 + bits.read(6)
                if len(pixels) + repeats > count:
                    raise ValueError('Compressed font run exceeds glyph size')
                pixels.extend([value] * repeats)
                previous = None
            else:
                previous = value
        if self.compression == 1:
            for index in range(width, count):
                pixels[index] ^= pixels[index - width]
        return pixels

    def destroy(self):
        self.destroyed = True
        self._glyphs.clear()
        self._glyf = b''


class BuiltinFont(int):
    """Keep the legacy Tk size interface, with real glyphs for symbols/fallbacks."""

    def __new__(cls, size, suffix=''):
        instance = super().__new__(cls, size)
        instance.fallback = None
        instance._bitmap = None
        instance._suffix = suffix
        return instance

    def bitmap(self):
        if self._bitmap is None:
            path = Path(__file__).with_name('fonts') / f'sim_montserrat_{int(self)}{self._suffix}.bin'
            self._bitmap = BinaryFont(path.read_bytes(), path)
        return self._bitmap

    @property
    def line_height(self):
        return self.bitmap().line_height

    @property
    def base_line(self):
        return self.bitmap().base_line


def bitmap_font(font):
    return font.bitmap() if isinstance(font, BuiltinFont) else font


def font_signature(font):
    result, visited = [], set()
    while font is not None:
        if id(font) in visited:
            raise ValueError('Font fallback cycle')
        visited.add(id(font))
        result.append((id(font), getattr(font, 'destroyed', False)))
        font = getattr(font, 'fallback', None)
    return tuple(result)


def resolve_glyph(font, code):
    visited = set()
    while font is not None:
        if id(font) in visited:
            raise ValueError('Font fallback cycle')
        visited.add(id(font))
        native = bitmap_font(font)
        if not isinstance(native, BinaryFont):
            raise TypeError('Expected an LVGL built-in or binary font')
        glyph = native.glyph(code)
        if glyph is not None:
            return native, glyph
        font = getattr(font, 'fallback', None)
    return None, None


def render_text(text, font, color, width=None):
    """Compose actual glyph alpha masks with kerning, wrapping, and fallback."""
    native = bitmap_font(font)
    native._check_alive()
    text = str(text).replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
    placeholder = Image.new('L', (max(3, native.size // 2), max(3, native.size * 3 // 4)))
    ImageDraw.Draw(placeholder).rectangle((0, 0, placeholder.width - 1, placeholder.height - 1), outline=255)
    missing = Glyph(placeholder.width + 1, 0, 0, placeholder)
    placements, x, line = [], 0.0, 0
    widest, min_x, min_y, max_x, max_y = 0.0, 0, 0, 0, native.line_height
    wrap_width = max(1, int(width)) if width is not None else None

    def glyphs_for(token):
        result = []
        for index, char in enumerate(token):
            owner, glyph = resolve_glyph(font, ord(char))
            glyph = glyph or missing
            kern = owner.kerning(ord(char), ord(token[index + 1])) if owner and index + 1 < len(token) else 0
            result.append((glyph, max(0, glyph.advance + kern)))
        return result

    for token in re.findall(r'\n|[^\S\n]+|[^\s]+', text):
        if token == '\n':
            widest, x, line = max(widest, x), 0.0, line + 1
            continue
        glyphs = glyphs_for(token)
        token_width = sum(advance for _, advance in glyphs)
        if wrap_width and x and x + token_width > wrap_width:
            widest, x, line = max(widest, x), 0.0, line + 1
            if token.isspace():
                continue
        for glyph, advance in glyphs:
            if wrap_width and x and x + advance > wrap_width:
                widest, x, line = max(widest, x), 0.0, line + 1
            left = round(x) + glyph.x
            top = line * native.line_height + native.ascent - glyph.y - glyph.mask.height
            placements.append((left, top, glyph.mask))
            min_x, min_y = min(min_x, left), min(min_y, top)
            max_x, max_y = max(max_x, left + glyph.mask.width), max(max_y, top + glyph.mask.height)
            x += advance
    widest = max(widest, x)
    max_y = max(max_y, (line + 1) * native.line_height)
    size = max(1, math.ceil(max(max_x, widest) - min_x)), max(1, max_y - min_y)
    if size[0] * size[1] > 16 * 1024 * 1024:
        raise ValueError('Rendered font label is too large')
    mask = Image.new('L', size)
    for left, top, glyph in placements:
        # Maximum alpha preserves overlapping glyph edges without erasing ink.
        if glyph.width and glyph.height:
            box = (left - min_x, top - min_y, left - min_x + glyph.width, top - min_y + glyph.height)
            mask.paste(ImageChops.lighter(mask.crop(box), glyph), box)
    result = Image.new('RGBA', size, color)
    result.putalpha(mask)
    return result
