"""Binary font decoding and real Tk rendering, without an application image."""
from pathlib import Path
import struct
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PIL import Image

from font_sim import BinaryFont, BuiltinFont, font_signature, render_text, resolve_glyph
import fs_driver_sim
import lvgl_sim as lv
from simulator import Simulator


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name('test-data') / 'fonts'


class BinaryFontTests(unittest.TestCase):
    def load(self, name='transit_16.bin'):
        path = ROOT / 'project' / 'fonts' / name
        font = BinaryFont(path.read_bytes(), path)
        if name in ('transit_16.bin', 'transit_28.bin'):
            font.fallback = BuiltinFont(font.size)
        return font

    def test_generated_fonts_contain_real_swedish_and_transport_glyphs(self):
        for name in ('transit_16.bin', 'transit_28.bin', 'transit_icons_32.bin'):
            font = self.load(name)
            for char in ('\uf207\uf238\uf21a' if 'icons' in name else 'ÅÄÖåäöÉé'):
                with self.subTest(font=name, char=char):
                    self.assertIsNotNone(font.glyph(ord(char)).mask.getbbox())
            if 'icons' not in name:
                self.assertEqual(len(font.cmap), 8)
                self.assertIsNone(font.glyph(ord('A')))
                self.assertIsNotNone(resolve_glyph(font, ord('A'))[1])
                self.assertEqual(resolve_glyph(font, ord(' '))[1].mask.size, (0, 0))
                expected_metrics = (21, 4) if font.size == 16 else (35, 6)
                self.assertEqual((font.line_height, font.base_line), expected_metrics)
        small = render_text('Bergåsa Station', self.load(), '#ffffff')
        large = render_text('Bergåsa Station', self.load('transit_28.bin'), '#ffffff')
        self.assertGreater(large.width, small.width)
        self.assertGreater(large.height, small.height)

    def test_all_documented_symbols_in_every_builtin_size(self):
        self.assertEqual(lv.SYMBOL.OK, '\uf00c')
        self.assertEqual(lv.SYMBOL.WIFI, '\uf1eb')
        for size in range(12, 50, 2):
            font = getattr(lv, f'font_montserrat_{size}')
            self.assertEqual(int(font), size)
            for name, symbol in vars(lv.SYMBOL).items():
                if name == 'DUMMY':  # Image-source marker, not a visible icon.
                    continue
                with self.subTest(size=size, symbol=name):
                    glyph = font.bitmap().glyph(ord(symbol))
                    self.assertIsNotNone(glyph)
                    self.assertIsNotNone(glyph.mask.getbbox())
        self.assertIsNone(lv.font_montserrat_16.bitmap().glyph(ord('Å')))

    def test_raw_and_both_compression_modes_match_at_each_bit_depth(self):
        for bpp in (1, 2, 3, 4, 8):
            raw = BinaryFont((FIXTURES / f'sample_{bpp}_raw.bin').read_bytes())
            self.assertEqual(raw.bpp, bpp)
            for mode in (() if bpp == 1 else ('rle', 'xor')):
                compressed = BinaryFont((FIXTURES / f'sample_{bpp}_{mode}.bin').read_bytes())
                self.assertEqual(raw.cmap, compressed.cmap)
                for code in raw.cmap:
                    with self.subTest(bpp=bpp, mode=mode, code=code):
                        first, second = raw.glyph(code), compressed.glyph(code)
                        self.assertEqual(first.advance, second.advance)
                        self.assertEqual((first.x, first.y, first.mask.size),
                                         (second.x, second.y, second.mask.size))
                        self.assertEqual(first.mask.tobytes(), second.mask.tobytes())
                self.assertEqual(render_text('AV ÅÄÖ åäö', raw, '#ffffff').tobytes(),
                                 render_text('AV ÅÄÖ åäö', compressed, '#ffffff').tobytes())

    def test_kerning_fallback_and_cycles(self):
        font = self.load()
        native = font.fallback.bitmap()
        self.assertLess(native.kerning(ord('A'), ord('V')), 0)
        pairs = BinaryFont((FIXTURES / 'sample_pairs.bin').read_bytes())
        self.assertTrue(pairs._pairs)
        self.assertIsNotNone(native._classes)
        self.assertEqual(native.kerning(ord('A'), ord('V')), pairs.kerning(ord('A'), ord('V')))
        icon_font = self.load('transit_icons_32.bin')
        icon_font.fallback = font
        font.fallback = BuiltinFont(16)
        self.assertIs(resolve_glyph(icon_font, ord('Å'))[0], font)
        self.assertIsNotNone(resolve_glyph(icon_font, ord(lv.SYMBOL.WIFI))[1])
        self.assertIsNone(resolve_glyph(icon_font, ord('漢'))[1])
        self.assertIsNotNone(render_text('Å ' + lv.SYMBOL.WIFI + ' \uf238', icon_font, '#ffffff').getbbox())
        font.fallback = icon_font
        with self.assertRaisesRegex(ValueError, 'cycle'):
            resolve_glyph(font, ord('漢'))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            font_signature(font)

    def test_registered_paths_buffers_legacy_names_and_lifecycle(self):
        with lv.filesystem(ROOT / 'project'):
            with self.assertRaisesRegex(ValueError, 'not registered'):
                lv.binfont_create('S:/fonts/transit_16.bin')
            fs_driver_sim.fs_register(lv.fs_drv_t(), 'S')
            font = lv.font_load('S:/fonts/transit_16.bin')
            with self.assertRaisesRegex(FileNotFoundError, 'Font is missing'):
                lv.binfont_create('S:/fonts/missing.bin')
            with self.assertRaisesRegex(ValueError, 'outside'):
                lv.binfont_create('S:/../outside.bin')
            lv.font_free(font)
            with self.assertRaisesRegex(ValueError, 'destroyed'):
                font.glyph(ord('A'))
            data = (ROOT / 'project/fonts/transit_16.bin').read_bytes()
            self.assertIsNotNone(lv.binfont_create_from_buffer(data, len(data)).glyph(ord('Å')))
            with self.assertRaisesRegex(ValueError, 'buffer size'):
                lv.binfont_create_from_buffer(data, len(data) + 1)

    def test_malformed_fonts_fail_explicitly(self):
        for data in (b'', b'bad font', b'\xff' * 64):
            with self.subTest(data=data[:8]):
                with self.assertRaises(ValueError):
                    BinaryFont(data)
        data = bytearray((ROOT / 'project/fonts/transit_16.bin').read_bytes())
        struct.pack_into('<I', data, 0, len(data) + 1)
        with self.assertRaisesRegex(ValueError, 'boundaries'):
            BinaryFont(data)

    def test_builtin_fallbacks_do_not_leak_between_runs(self):
        original = lv.font_montserrat_16.fallback
        try:
            with lv.filesystem(ROOT / 'project'):
                font = self.load()
                lv.font_montserrat_16.fallback = font
                with lv.filesystem(ROOT):
                    self.assertIsNone(lv.font_montserrat_16.fallback)
                self.assertIs(lv.font_montserrat_16.fallback, font)
            self.assertIs(lv.font_montserrat_16.fallback, original)
        finally:
            lv.font_montserrat_16.fallback = original


class FontRenderingTests(unittest.TestCase):
    def setUp(self):
        self.window = tk.Tk()
        self.window.withdraw()
        self.addCleanup(self.window.destroy)
        self.canvas = tk.Canvas(self.window, width=600, height=450)
        lv.setup(self.canvas)
        context = lv.filesystem(ROOT / 'project')
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        fs_driver_sim.fs_register(lv.fs_drv_t(), 'S')
        self.font = lv.binfont_create('S:/fonts/transit_16.bin')
        self.font.fallback = lv.font_montserrat_16
        self.view = lv.tileview(lv.screen_active())
        self.view.set_size(600, 450)
        self.tile = self.view.add_tile(0, 0, lv.DIR.NONE)
        self.tile.set_style_text_font(self.font, 0)

    def photo_pixels(self, photo):
        from io import BytesIO
        png = self.canvas.tk.call(str(photo), 'data', '-format', 'png')
        return Image.open(BytesIO(png)).convert('RGBA')

    def test_real_glyphs_inheritance_click_targets_themes_and_cache(self):
        caption = lv.label(self.tile)
        text = 'ÅÄÖ åäö Gralén ' + lv.SYMBOL.OK + lv.SYMBOL.WIFI
        caption.set_text(text)
        caption.center()
        caption.add_flag(lv.obj.FLAG.CLICKABLE)
        clicked = Mock()
        caption.add_event_cb(clicked, lv.EVENT.CLICKED, None)
        app = Simulator.__new__(Simulator)
        app.canvas = self.canvas
        app.invoke = lambda action: (action(), app.refresh())
        app.refresh()
        self.assertIs(caption.font, self.font)
        self.assertEqual(caption.get_text(), text)
        photo = caption._text_images['text'][1]
        actual = self.photo_pixels(photo)
        expected = render_text(text, self.font, '#000000')
        self.assertEqual(actual.size, expected.size)
        self.assertEqual(actual.tobytes(), expected.tobytes())
        bounds = next(hit[:4] for hit in app.hits if hit[-1] is caption)
        touch = SimpleNamespace(x=(bounds[0] + bounds[2])/2, y=(bounds[1] + bounds[3])/2)
        app.down(touch)
        app.up(touch)
        clicked.assert_called_once()
        self.assertIs(caption._text_images['text'][1], photo)
        self.tile.set_style_text_color('#ffffff', 0)
        app.refresh()
        changed = self.photo_pixels(caption._text_images['text'][1])
        self.assertEqual(changed.getchannel('A').tobytes(), actual.getchannel('A').tobytes())
        pixels = changed.tobytes()
        self.assertTrue(all(pixels[i:i+3] == b'\xff\xff\xff'
                            for i in range(0, len(pixels), 4) if pixels[i+3]))

    def test_symbols_fallback_multiline_and_dropdowns(self):
        caption = lv.label(self.tile)
        self.font.fallback = lv.font_montserrat_16
        caption.set_text(lv.SYMBOL.OK + ' Apply\n' + lv.SYMBOL.WIFI + ' ÅÄÖ')
        caption.set_width(150)
        dropdown = lv.dropdown(self.tile)
        dropdown.set_pos(250, 50)
        dropdown.set_options('Bergåsa Station\n' + lv.SYMBOL.WIFI + ' Gräsvik')
        dropdown.open()
        lv.render()
        self.assertIn('text', caption._text_images)
        self.assertIn('caption', dropdown._text_images)
        self.assertEqual(set(dropdown.popup._text_images), {'row0', 'row1'})
        photo = caption._text_images['text'][1]
        self.assertGreater(photo.height(), self.font.line_height)
        caption.set_style_text_font(lv.font_montserrat_28, 0)
        caption.set_text(lv.SYMBOL.OK + lv.SYMBOL.WIFI + lv.SYMBOL.PLAY)
        lv.render()
        self.assertIsNot(caption._text_images['text'][1], photo)

    def test_image_symbol_sources_dummy_prefix_and_source_changes(self):
        icon = lv.image(self.tile)
        icon.set_style_text_font(lv.font_montserrat_28, 0)
        icon.set_src(lv.SYMBOL.WIFI)
        icon.center()
        lv.render()
        expected = render_text(lv.SYMBOL.WIFI, lv.font_montserrat_28, '#000000')
        self.assertEqual(self.photo_pixels(icon._text_images['symbol'][1]).tobytes(), expected.tobytes())
        self.assertEqual((icon.width, icon.height), expected.size)
        icon.set_style_text_font(self.font, 0)
        icon.set_src(lv.SYMBOL.DUMMY + 'Bergåsa ' + lv.SYMBOL.WIFI)
        lv.render()
        self.assertEqual(icon.get_src(), lv.SYMBOL.DUMMY + 'Bergåsa ' + lv.SYMBOL.WIFI)
        expected = render_text('Bergåsa ' + lv.SYMBOL.WIFI, self.font, '#000000')
        self.assertEqual(self.photo_pixels(icon._text_images['symbol'][1]).tobytes(), expected.tobytes())
        icon_font = lv.binfont_create('S:/fonts/transit_icons_32.bin')
        icon.set_style_text_font(icon_font, 0)
        icon.set_src('\uf238')
        lv.render()
        expected = render_text('\uf238', icon_font, '#000000')
        self.assertEqual(self.photo_pixels(icon._text_images['symbol'][1]).tobytes(), expected.tobytes())
        icon.set_src('S:/assets/QR_Black_On_White.png')
        lv.render()
        self.assertIsNone(icon._symbol_text)
        self.assertIsNotNone(icon._photo)
        icon.set_src(None)
        lv.render()
        self.assertEqual((icon.width, icon.height), (0, 0))
        self.assertFalse(icon._text_images)


if __name__ == '__main__':
    unittest.main()
