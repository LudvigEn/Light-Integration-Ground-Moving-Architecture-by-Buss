"""Integration checks: real image extraction, boot, touch callbacks, reset state."""
import argparse
import ast
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from fat_image import FatImage, TruncatedImageError
from simulator import Simulator, Network, DEFAULT_IMAGE, runtime, extract_image
import lvgl_sim as lv
import fs_driver_sim

IMAGE = DEFAULT_IMAGE


class WidgetTests(unittest.TestCase):
    """Exercise controls and gestures without creating a desktop window."""

    def setUp(self):
        self.canvas = Mock()
        lv.setup(self.canvas)
        self.view = lv.tileview(lv.screen_active())
        self.view.set_size(600, 450)
        self.tile = self.view.add_tile(0, 0, lv.DIR.RIGHT)
        self.other_tile = self.view.add_tile(1, 0, lv.DIR.LEFT)
        self.app = Simulator.__new__(Simulator)
        self.app.canvas = self.canvas
        self.app.invoke = lambda action: (action(), self.app.refresh())
        self.app.refresh()

    def overflow(self):
        row = lv.obj(self.tile)
        row.set_pos(75, 700)
        row.set_size(450, 60)
        self.app.refresh()
        return row

    def test_swipe_refreshes_departure_tile_without_accumulating_rows(self):
        calls = []

        def refresh_departures(event):
            self.assertIs(event.get_target_obj(), self.view)
            if self.view.get_tile_active() == self.other_tile:
                self.other_tile.clean()
                row = lv.obj(self.other_tile)
                lv.label(row).set_text('Updated departures')
                calls.append(row)

        self.view.add_event_cb(refresh_departures, lv.EVENT.VALUE_CHANGED, None)
        for _ in range(2):
            self.view.set_tile(self.tile)
            self.app.down(SimpleNamespace(x=500, y=200))
            self.app.up(SimpleNamespace(x=100, y=200))
            self.assertIs(self.view.get_tile_active(), self.other_tile)
            self.assertEqual(len(self.other_tile.children), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].children, [])
        self.view.move(1, 0)  # No tile exists further to the right.
        self.view.set_tile(self.other_tile)  # Already active.
        self.assertEqual(len(calls), 2)

    def test_dropdown_selection_through_touch(self):
        control = lv.dropdown(self.tile)
        control.set_pos(20, 60)
        control.set_options('First\nSecond\nThird')
        changes = []
        control.add_event_cb(lambda event: changes.append(event.get_target().get_selected()),
                             lv.EVENT.VALUE_CHANGED, None)
        control.set_selected(2)
        self.assertEqual(changes, [])
        self.assertEqual(control.get_options(), 'First\nSecond\nThird')
        self.assertEqual(control.get_option_count(), 3)
        self.app.refresh()
        touch = SimpleNamespace(x=30, y=70)
        self.app.down(touch)
        self.app.up(touch)
        self.assertTrue(control.is_open())
        choice = SimpleNamespace(x=30, y=140)
        self.app.down(choice)
        self.app.up(choice)
        self.assertEqual(control.get_selected(), 1)
        self.assertEqual(changes, [1])
        self.assertFalse(control.is_open())

    def test_dropdown_dismiss_and_disabled(self):
        control = lv.dropdown(self.tile)
        control.open()
        self.app.refresh()
        outside = SimpleNamespace(x=500, y=400)
        self.app.down(outside)
        self.app.up(outside)
        self.assertFalse(control.is_open())
        control.add_state(lv.STATE.DISABLED)
        control.click()
        self.assertFalse(control.is_open())
        control.set_options('')
        control.remove_state(lv.STATE.DISABLED)
        control.click()
        self.assertFalse(control.is_open())

    def test_dropdown_popup_tracks_theme_while_open(self):
        control = lv.dropdown(self.tile)
        control.set_options('First\nSecond')
        control.open()
        for background, foreground in [('#303030', '#ffffff'), ('#e0e0e0', '#000000')]:
            with self.subTest(background=background):
                control.set_style_bg_color(background, lv.PART.MAIN)
                control.set_style_text_color(foreground, lv.PART.MAIN)
                self.canvas.reset_mock()
                self.app.refresh()
                rows = self.canvas.create_rectangle.call_args_list[-2:]
                texts = self.canvas.create_text.call_args_list[-2:]
                self.assertEqual([row.kwargs['fill'] for row in rows], ['#476582', background])
                self.assertEqual([text.kwargs['fill'] for text in texts], ['#ffffff', foreground])

    def test_dropdown_list_styles_are_separate_from_control(self):
        control = lv.dropdown(self.tile)
        control.set_options('First\nSecond')
        control.set_style_bg_color('#303030', 0)
        popup = control.get_list()
        popup.set_style_bg_color('#222222', lv.PART.MAIN)
        popup.set_style_text_color('#eeeeee', lv.PART.MAIN)
        popup.set_style_bg_color('#123456', lv.PART.SELECTED)
        popup.set_style_text_color('#abcdef', lv.PART.SELECTED | lv.STATE.CHECKED)
        control.open()
        self.canvas.reset_mock()
        self.app.refresh()
        rows = self.canvas.create_rectangle.call_args_list[-2:]
        texts = self.canvas.create_text.call_args_list[-2:]
        self.assertEqual([row.kwargs['fill'] for row in rows], ['#123456', '#222222'])
        self.assertEqual([text.kwargs['fill'] for text in texts], ['#abcdef', '#eeeeee'])
        self.assertEqual(control.bg, '#303030')
        self.assertEqual(control.fg, '#000000')
        control.close()
        control.open()
        self.assertIs(control.get_list(), popup)

    def test_button_border_changes_color_and_can_be_removed(self):
        control = lv.button(self.tile)
        control.set_pos(75, 260)
        control.set_size(200, 50)
        control.set_style_border_width(2, lv.PART.MAIN)
        for color in ('#ffffff', '#000000'):
            control.set_style_border_color(color, lv.PART.MAIN)
            self.canvas.reset_mock()
            self.app.refresh()
            border = self.canvas.create_rectangle.call_args
            self.assertEqual(border.args, (76, 261, 274, 309))
            self.assertEqual(border.kwargs, {'fill': '', 'outline': color, 'width': 2})
        control.set_style_border_width(0, lv.PART.MAIN)
        self.canvas.reset_mock()
        self.app.refresh()
        self.assertFalse(any(call.kwargs.get('width')
                             for call in self.canvas.create_rectangle.call_args_list))

    def test_button_label_inherits_theme_with_explicit_override(self):
        control = lv.button(self.tile)
        caption = lv.label(control)
        caption.set_text('SAVE')
        caption.center()
        for foreground in ('#ffffff', '#000000'):
            control.set_style_text_color(foreground, lv.PART.MAIN)
            self.app.refresh()
            self.assertEqual(self.canvas.create_text.call_args.kwargs['fill'], foreground)
        caption.set_style_text_color('#ff0000', 0)
        control.set_style_text_color('#ffffff', 0)
        self.app.refresh()
        self.assertEqual(self.canvas.create_text.call_args.kwargs['fill'], '#ff0000')

    def test_departure_rows_use_current_columns_without_duplicates(self):
        # Load the actual Application class without hardware or secrets imports.
        source = Path(__file__).resolve().parents[1] / 'project' / 'main.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        application = next(node for node in tree.body
                           if isinstance(node, ast.ClassDef) and node.name == 'Application')
        namespace = {'lv': lv, 'log': lambda message: None}
        exec(compile(ast.Module(body=[application], type_ignores=[]), str(source), 'exec'), namespace)
        app = namespace['Application'].__new__(namespace['Application'])
        app.tileview = lv.tileview(lv.screen_active())
        app.tileview.set_size(600, 450)
        app.backgrounds, app.borders, app.labels = [], [], []
        app.controls = []
        app.dep_scr = app.tileview.add_tile(2, 0, lv.DIR.LEFT)
        app.dark_mode = True
        route = SimpleNamespace(designation='1', direction='Lyckeby', destination='Centrum')
        departure = SimpleNamespace(route=route, realtime=None,
                                    scheduled='2026-09-18T16:44:40', delay=0, canceled=False)
        updated = SimpleNamespace(route=route, realtime='2026-09-18T17:05:00',
                                  scheduled='2026-09-18T17:00:00', delay=300, canceled=False)
        stop = SimpleNamespace(name='Campus Gräsvik', departures=[departure, updated])
        for _ in range(2):
            app.clear_departures()
            app.create_departure_screen(stop)
            self.assertEqual(app.dep_scr.children[0].get_text(), stop.name)
            rows = app.dep_scr.children[1:]
            self.assertEqual(len(rows), 3)  # Heading plus two departures.
            texts = [[cell.children[0].children[0].get_text() for cell in row.children]
                     for row in rows]
            self.assertEqual(texts, [
                ['Route', 'Destination', 'ETA', 'Delay'],
                ['1', 'Centrum', '16:44:40', '0s'],
                ['1', 'Centrum', '17:05:00', '+5m 0s'],
            ])
            for row in rows:
                for box in [row] + row.children + [cell.children[0] for cell in row.children]:
                    self.assertFalse(box.has_flag(lv.obj.FLAG.SCROLLABLE))
                    self.assertEqual(box.border_width, 0)

    def test_event_object_accessors_and_parameter(self):
        events = []
        marker = object()
        self.tile.add_event_cb(events.append, lv.EVENT.VALUE_CHANGED, 'user data')
        self.tile.send_event(lv.EVENT.VALUE_CHANGED, marker)
        event = events[0]
        self.assertIs(event.get_target_obj(), self.tile)
        self.assertIs(event.get_current_target_obj(), self.tile)
        self.assertIs(event.get_param(), marker)
        self.assertEqual(event.get_user_data(), 'user data')

    def test_device_font_preview_preserves_underlying_unicode(self):
        caption = lv.label(self.tile)
        caption.set_text('ÅÄÖ åäö BUS')
        self.app.refresh()
        self.assertEqual(caption.get_text(), 'ÅÄÖ åäö BUS')
        self.assertEqual(self.canvas.create_text.call_args.kwargs['text'], '□□□ □□□ BUS')
        self.tile.set_style_text_font(lv.font_montserrat_28, 0)
        self.app.refresh()
        self.assertEqual(self.canvas.create_text.call_args.kwargs['font'], ('Arial', -28))

    def test_switch_checked_events_and_disabled(self):
        control = lv.switch(self.tile)
        changes = []
        clicks = []
        control.add_event_cb(
            lambda event: changes.append((event.get_target().has_state(lv.STATE.CHECKED),
                                          event.get_code(), event.get_user_data())),
            lv.EVENT.VALUE_CHANGED, 'dark mode',
        )
        control.add_event_cb(lambda event: clicks.append(event.get_code()), lv.EVENT.CLICKED, None)
        control.add_state(lv.STATE.CHECKED)
        self.assertEqual(changes, [])
        control.click()
        control.click()
        self.assertEqual(changes, [(False, lv.EVENT.VALUE_CHANGED, 'dark mode'),
                                   (True, lv.EVENT.VALUE_CHANGED, 'dark mode')])
        self.assertEqual(clicks, [lv.EVENT.CLICKED, lv.EVENT.CLICKED])
        control.add_state(lv.STATE.DISABLED)
        control.click()
        self.assertEqual(len(changes), 2)
        control.remove_state(lv.STATE.CHECKED | lv.STATE.DISABLED)
        self.assertFalse(control.has_state(lv.STATE.CHECKED))

    def test_switch_clicks_without_callback_and_draws_knob(self):
        control = lv.switch(self.tile)
        control.set_pos(250, 75)
        self.app.refresh()
        off_knob = self.canvas.create_oval.call_args.args
        event = SimpleNamespace(x=275, y=90)
        self.app.down(event)
        self.app.up(event)
        self.assertTrue(control.has_state(lv.STATE.CHECKED))
        on_knob = self.canvas.create_oval.call_args.args
        self.assertGreater(on_knob[0], off_knob[0])

    def test_drag_scroll_clamps_and_preserves_horizontal_swipe(self):
        row = self.overflow()
        self.assertFalse(any(hit[-1] is row for hit in self.app.hits))
        self.app.down(SimpleNamespace(x=300, y=350))
        self.app.drag(SimpleNamespace(x=300, y=150))
        self.assertEqual(self.tile.get_scroll_y(), 200)
        self.app.up(SimpleNamespace(x=300, y=-100))
        self.assertEqual(self.tile.get_scroll_y(), 310)
        self.assertEqual(self.view.active, (0, 0))
        row_hit = next(hit for hit in self.app.hits if hit[-1] is row)
        self.assertEqual(row_hit[:4], (75, 390, 525, 450))
        self.app.down(SimpleNamespace(x=500, y=200))
        self.app.up(SimpleNamespace(x=100, y=200))
        self.assertEqual(self.view.active, (1, 0))
        self.app.move(-1, 0)
        self.assertEqual(self.tile.get_scroll_y(), 310)
        self.app.down(SimpleNamespace(x=300, y=100))
        self.app.up(SimpleNamespace(x=300, y=500))
        self.assertEqual(self.tile.get_scroll_y(), 0)

    def test_wheel_limits_flags_and_direction(self):
        self.overflow()
        self.app.wheel(SimpleNamespace(x=200, y=200, delta=-120))
        self.assertEqual(self.tile.get_scroll_y(), 60)
        self.tile.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.app.wheel(SimpleNamespace(x=200, y=200, delta=-120))
        self.assertEqual(self.tile.get_scroll_y(), 60)
        self.tile.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.tile.set_scroll_dir(lv.DIR.HOR)
        self.app.wheel(SimpleNamespace(x=200, y=200, delta=-120))
        self.assertEqual(self.tile.get_scroll_y(), 60)
        self.tile.set_scroll_dir(lv.DIR.VER)
        self.app.wheel(SimpleNamespace(x=200, y=200), 10000)
        self.assertEqual(self.tile.get_scroll_y(), 310)
        self.app.wheel(SimpleNamespace(x=200, y=200), -10000)
        self.assertEqual(self.tile.get_scroll_y(), 0)

    def test_scroll_drag_does_not_click_and_clips_hit_targets(self):
        self.overflow()
        control = lv.switch(self.tile)
        control.set_pos(75, 100)
        self.app.refresh()
        self.app.down(SimpleNamespace(x=80, y=110))
        self.app.up(SimpleNamespace(x=80, y=70))
        self.assertFalse(control.has_state(lv.STATE.CHECKED))
        self.tile.scroll_to_y(110)
        self.app.refresh()
        hit = next(hit for hit in self.app.hits if hit[-1] is control)
        self.assertEqual(hit[1], 0)
        self.assertEqual(hit[3], 18)
        self.tile.scroll_to_y(200)
        self.app.refresh()
        self.assertFalse(any(hit[-1] is control for hit in self.app.hits))

    def test_vertical_tile_navigation_when_content_fits(self):
        self.tile.directions |= lv.DIR.BOTTOM
        self.view.add_tile(0, 1, lv.DIR.TOP)
        self.app.down(SimpleNamespace(x=300, y=350))
        self.app.up(SimpleNamespace(x=300, y=100))
        self.assertEqual(self.view.active, (0, 1))

    def test_image_dialog_defaults_and_cancel(self):
        self.app.restart = Mock()
        with patch('simulator.filedialog.askopenfilename', return_value='') as choose:
            self.app.choose()
        self.assertEqual(choose.call_args.kwargs['initialdir'], str(DEFAULT_IMAGE.parent))
        self.assertEqual(choose.call_args.kwargs['initialfile'], 't4s3-vfs.img')
        self.app.restart.assert_not_called()


class ImageTests(unittest.TestCase):
    """Real Tk PNG decoding, device paths, theme changes, and vertical swipes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.window = tk.Tk()
        self.window.withdraw()
        self.addCleanup(self.window.destroy)
        self.canvas = tk.Canvas(self.window, width=600, height=450)
        lv.setup(self.canvas)
        self.view = lv.tileview(lv.screen_active())
        self.view.set_size(600, 450)
        self.settings = self.view.add_tile(1, 0, lv.DIR.BOTTOM)
        self.qr_tile = self.view.add_tile(1, 1, lv.DIR.TOP)
        self.view.set_tile(self.settings)
        assets = self.root / 'assets'
        assets.mkdir()
        for name, background, foreground in [
            ('QR_Black_On_White.png', 'white', 'black'),
            ('QR_White_On_Black.png', 'black', 'white'),
        ]:
            photo = tk.PhotoImage(master=self.canvas, width=4, height=4)
            photo.put(background, to=(0, 0, 4, 4))
            photo.put(foreground, to=(1, 1, 3, 3))
            photo.write(str(assets / name), format='png')
        transparent = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        transparent.paste((0, 0, 0, 255), (1, 1, 3, 3))
        transparent.save(assets / 'transparent.png')
        self.fs_context = lv.filesystem(self.root)
        self.fs_context.__enter__()
        self.addCleanup(self.fs_context.__exit__, None, None, None)
        self.driver = lv.fs_drv_t()
        fs_driver_sim.fs_register(self.driver, 'S')

    def test_png_rendering_theme_switch_and_vertical_swipes(self):
        qr = lv.image(self.qr_tile)
        qr.center()
        qr.set_src('S:/assets/transparent.png')
        switch = lv.switch(self.settings)
        switch.set_pos(250, 200)
        switch.add_state(lv.STATE.CHECKED)

        def apply_theme(_event=None):
            dark = switch.has_state(lv.STATE.CHECKED)
            self.qr_tile.set_style_bg_color('#000000' if dark else '#ffffff', 0)
            qr.set_style_image_recolor('#ffffff' if dark else '#000000', 0)
            qr.set_style_image_recolor_opa(lv.OPA.COVER, 0)

        switch.add_event_cb(apply_theme, lv.EVENT.VALUE_CHANGED, None)
        apply_theme()
        self.assertEqual(qr._photo.get(1, 1), (255, 255, 255))
        self.assertTrue(qr._photo.transparency_get(0, 0))
        self.assertFalse(qr._photo.transparency_get(1, 1))
        self.assertEqual((qr.width, qr.height), (4, 4))

        simulator = Simulator.__new__(Simulator)
        simulator.canvas = self.canvas
        simulator.invoke = lambda action: (action(), simulator.refresh())
        simulator.refresh()
        simulator.down(SimpleNamespace(x=300, y=350))
        simulator.up(SimpleNamespace(x=300, y=100))
        self.assertIs(self.view.get_tile_active(), self.qr_tile)
        images = [item for item in self.canvas.find_all() if self.canvas.type(item) == 'image']
        self.assertEqual(len(images), 1)
        self.assertEqual(self.canvas.coords(images[0]), [298, 223])
        self.assertEqual(self.canvas.itemcget(images[0], 'image'), str(qr._photo))
        self.assertEqual(qr.get_src(), 'S:/assets/transparent.png')

        simulator.down(SimpleNamespace(x=300, y=100))
        simulator.up(SimpleNamespace(x=300, y=350))
        self.assertIs(self.view.get_tile_active(), self.settings)
        self.assertFalse(any(self.canvas.type(item) == 'image' for item in self.canvas.find_all()))
        simulator.down(SimpleNamespace(x=275, y=215))
        simulator.up(SimpleNamespace(x=275, y=215))
        self.assertEqual(qr.get_src(), 'S:/assets/transparent.png')
        self.assertEqual(qr._photo.get(1, 1), (0, 0, 0))
        self.assertTrue(qr._photo.transparency_get(0, 0))
        simulator.move(0, 1)
        self.assertIs(self.view.get_tile_active(), self.qr_tile)
        self.assertTrue(any(self.canvas.type(item) == 'image' for item in self.canvas.find_all()))

    def test_recolor_opacity_preserves_original_pixels_and_alpha(self):
        source = Image.new('RGBA', (3, 1))
        source.putdata([(20, 40, 60, 255), (100, 80, 60, 128), (0, 0, 0, 0)])
        source.save(self.root / 'assets' / 'alpha.png')
        qr = lv.image(self.qr_tile)
        # Styles can be set before loading a source.
        qr.set_style_image_recolor('#c86432', 0)
        qr.set_style_image_recolor_opa(128, 0)
        qr.set_src('S:/assets/alpha.png')
        png = self.canvas.tk.call(str(qr._photo), 'data', '-format', 'png')
        rendered = Image.open(BytesIO(png))
        self.assertEqual(rendered.convert('RGBA').getchannel('A').tobytes(),
                         source.getchannel('A').tobytes())
        self.assertEqual(qr._photo.get(0, 0), (110, 70, 54))
        self.assertTrue(qr._photo.transparency_get(2, 0))
        qr.set_style_image_recolor_opa(lv.OPA.TRANSP, 0)
        self.assertEqual(qr._photo.get(0, 0), (20, 40, 60))
        qr.set_style_image_recolor_opa(lv.OPA.COVER, 0)
        self.assertEqual(qr._photo.get(0, 0), (200, 100, 50))
        photo = qr._photo
        qr.set_style_image_recolor('#c86432', 0)
        qr.set_style_image_recolor_opa(lv.OPA.COVER, 0)
        self.assertIs(qr._photo, photo)
        qr.set_src(None)
        qr.set_src('S:/assets/alpha.png')
        self.assertEqual(qr._photo.get(0, 0), (200, 100, 50))
        # Recoloring tints opaque backgrounds too; it is not color inversion.
        qr.set_src('S:/assets/QR_Black_On_White.png')
        self.assertEqual(qr._photo.get(0, 0), (200, 100, 50))
        self.assertFalse(qr._photo.transparency_get(0, 0))

    def test_project_transparent_qr_recolors_in_both_themes(self):
        project = Path(__file__).resolve().parents[1] / 'project'
        with lv.filesystem(project):
            fs_driver_sim.fs_register(lv.fs_drv_t(), 'S')
            qr = lv.image(self.qr_tile)
            qr.set_src('S:/assets/QR_Black_On_White.png')
            alpha = qr._pixels.getchannel('A').tobytes()
            self.assertIn(0, alpha)
            self.assertIn(255, alpha)
            module = next((x, y) for y in range(qr.height) for x in range(qr.width)
                          if qr._pixels.getpixel((x, y))[3] == 255)
            for color, rgb in [('#ffffff', (255, 255, 255)), ('#000000', (0, 0, 0))]:
                qr.set_style_image_recolor(color, 0)
                qr.set_style_image_recolor_opa(lv.OPA.COVER, 0)
                self.assertEqual(qr._photo.get(*module), rgb)
                self.assertTrue(qr._photo.transparency_get(0, 0))
                self.assertEqual(qr._pixels.getchannel('A').tobytes(), alpha)

    def test_source_cache_clearing_and_native_size(self):
        qr = lv.image(self.qr_tile)
        qr.set_src('S:assets/QR_Black_On_White.png')
        photo = qr._photo
        qr.set_src(qr.get_src())
        self.assertIs(qr._photo, photo)
        self.assertEqual((qr.width, qr.height), (4, 4))
        qr.set_src(None)
        self.assertIsNone(qr.get_src())
        self.assertIsNone(qr._photo)
        self.assertEqual((qr.width, qr.height), (0, 0))
        qr.set_src('S:/assets/QR_White_On_Black.png')
        qr.delete()
        self.assertIsNone(qr._photo)
        self.assertNotIn(qr, self.qr_tile.children)

    def test_project_qr_pngs_decode_at_native_size(self):
        project = Path(__file__).resolve().parents[1] / 'project'
        with lv.filesystem(project):
            fs_driver_sim.fs_register(lv.fs_drv_t(), 'S')
            qr = lv.image(self.qr_tile)
            qr.center()
            self.view.set_tile(self.qr_tile)
            files = sorted((project / 'assets').glob('QR_*.png'))
            self.assertTrue(files, 'No project QR images found')
            for path in files:
                qr.set_src('S:/assets/' + path.name)
                self.assertGreater(qr.width, 0)
                self.assertGreater(qr.height, 0)
                lv.render()
                items = [item for item in self.canvas.find_all() if self.canvas.type(item) == 'image']
                self.assertEqual(len(items), 1)
                self.assertEqual(self.canvas.coords(items[0]),
                                 [(600 - qr.width) / 2, (450 - qr.height) / 2])

    def test_invalid_drive_missing_file_and_vfs_escape(self):
        qr = lv.image(self.qr_tile)
        with self.assertRaisesRegex(ValueError, 'not registered'):
            qr.set_src('Z:/assets/qr.png')
        with self.assertRaisesRegex(ValueError, 'registered LVGL drive'):
            qr.set_src('/assets/qr.png')
        with self.assertRaisesRegex(FileNotFoundError, 'missing from the filesystem image'):
            qr.set_src('S:/assets/missing.png')
        with self.assertRaisesRegex(ValueError, 'outside the simulated filesystem'):
            qr.set_src('S:/../outside.png')
        with self.assertRaises(ValueError):
            fs_driver_sim.fs_register(lv.fs_drv_t(), 'LONG')

    def test_fs_driver_import_and_registration_are_isolated(self):
        import sys
        previous = sys.modules.get('fs_driver')
        with tempfile.TemporaryDirectory() as other:
            with runtime(Path(other), Network(True)):
                import fs_driver
                self.assertIs(fs_driver, fs_driver_sim)
                with self.assertRaisesRegex(ValueError, 'not registered'):
                    lv.image_path('S:/assets/QR_Black_On_White.png')
                fs_driver.fs_register(lv.fs_drv_t(), 'S')
                with self.assertRaises(FileNotFoundError):
                    lv.image_path('S:/assets/QR_Black_On_White.png')
            self.assertIs(sys.modules.get('fs_driver'), previous)
            self.assertEqual(lv.image_path('S:/assets/QR_Black_On_White.png'),
                             self.root / 'assets' / 'QR_Black_On_White.png')


class SimulatorTests(unittest.TestCase):
    def test_truncated_deployment_uses_matching_full_image(self):
        original = Path(IMAGE).read_bytes()
        # A valid filesystem header with the remainder cut off must not cause
        # the simulator to fabricate the missing data or ignore allocated files.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            trimmed = root / 't4s3-vfs-deploy.img'
            full = root / 't4s3-vfs.img'
            trimmed.write_bytes(original[:512])
            full.write_bytes(original)
            with self.assertRaises(TruncatedImageError):
                FatImage(trimmed).files()
            destination = root / 'extracted'
            self.assertEqual(extract_image(trimmed, destination), full)
            self.assertEqual((destination / 'main.py').read_bytes(), FatImage(full).files()['main.py'])
            self.assertEqual(trimmed.read_bytes(), original[:512])

    def test_truncated_image_without_matching_full_image_still_fails(self):
        original = Path(IMAGE).read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            trimmed = root / 't4s3-vfs-deploy.img'
            trimmed.write_bytes(original[:512])
            with self.assertRaises(TruncatedImageError):
                extract_image(trimmed, root / 'extracted')
            different = bytearray(original)
            different[3] ^= 1  # Change the OEM identifier, leaving FAT geometry intact.
            (root / 't4s3-vfs.img').write_bytes(different)
            with self.assertRaisesRegex(ValueError, 'different build'):
                extract_image(trimmed, root / 'extracted')
            custom = root / 'other.img'
            custom.write_bytes(original[:512])
            with self.assertRaises(TruncatedImageError):
                extract_image(custom, root / 'extracted')

    def test_full_and_deployment_images_share_saved_settings(self):
        app = Simulator.__new__(Simulator)
        app.state_dir = Path('test-state')
        app.source = DEFAULT_IMAGE
        full_settings = app.settings_path()
        app.source = DEFAULT_IMAGE.with_name('t4s3-vfs-deploy.img')
        self.assertEqual(app.settings_path(), full_settings)

    def test_image_roundtrip(self):
        files = FatImage(IMAGE).files()
        self.assertIn('main.py', files)
        self.assertIn('board_lvgl.py', files)
        with tempfile.TemporaryDirectory() as folder:
            FatImage(IMAGE).extract(folder)
            for name, data in files.items():
                self.assertEqual((Path(folder) / name).read_bytes(), data)

    def test_invalid_image(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.img'
            path.write_bytes(b'not a filesystem')
            with self.assertRaises(ValueError):
                FatImage(path)

    def test_boot_swipe_click(self):
        before = hashlib.sha256(Path(IMAGE).read_bytes()).digest()
        # Exercise startup without an explicit filename for the default image.
        source = None if Path(IMAGE).resolve() == DEFAULT_IMAGE else IMAGE
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        app = Simulator(source, hidden=True, local_data=True, state_dir=state.name)
        try:
            self.assertEqual(app.source, Path(IMAGE).resolve())
            app.boot()
            self.assertIn('app', app.scope, app.console.get('1.0', 'end'))
            target = app.scope['app']
            self.assertEqual(target.tileview.active, (0, 0))
            app.down(SimpleNamespace(x=500, y=200))
            app.up(SimpleNamespace(x=100, y=200))
            self.assertEqual(target.tileview.active, (1, 0))
            self.assertTrue(target.dark_mode)
            self.assertTrue(target.dark_mode_switch.has_state(lv.STATE.CHECKED))
            self.assertEqual(target.transport_type_dropdown.get_options(), 'BUS\nTRAIN')
            self.assertEqual(target.stop_dropdown.get_selected(), 0)
            app.down(SimpleNamespace(x=275, y=215))
            app.up(SimpleNamespace(x=275, y=215))
            self.assertFalse(target.dark_mode)
            self.assertEqual(target.settings_screen.bg, '#ffffff')
            self.assertTrue(all(label.fg == '#000000' for label in target.labels))
            app.down(SimpleNamespace(x=275, y=215))
            app.up(SimpleNamespace(x=275, y=215))
            self.assertTrue(target.dark_mode)
            self.assertEqual(target.settings_screen.bg, '#000000')
            self.assertTrue(all(label.fg == '#ffffff' for label in target.labels))
            app.move(1, 0)
            self.assertEqual(target.tileview.active, (2, 0))
            self.assertGreater(len(target.dep_scr.children), 2, app.console.get('1.0', 'end'))
            self.assertIn('Fetch and parsing data:', app.console.get('1.0', 'end'))
            self.assertIn('Rendering Departure-screen:', app.console.get('1.0', 'end'))
            row_count = len(target.dep_scr.children)
            app.move(-1, 0)
            app.move(1, 0)
            self.assertEqual(len(target.dep_scr.children), row_count)
            app.network.online = False
            app.move(-1, 0)
            app.move(1, 0)
            self.assertEqual(target.dep_scr.children[0].get_text(),
                             'Could not load departures. Try again!')
            app.network.online = True
            app.move(-1, 0)
            app.move(1, 0)
            self.assertEqual(len(target.dep_scr.children), row_count)
            app.wheel(SimpleNamespace(x=300, y=200, delta=-120))
            self.assertGreater(target.dep_scr.get_scroll_y(), 0)
            self.assertEqual(target.tileview.active, (2, 0))
            app.move(-1, 0)
            app.move(-1, 0)
            self.assertEqual(target.tileview.active, (0, 0))
            self.assertTrue((app.root / 'debug.log').exists())
        finally:
            app.close()
        self.assertEqual(hashlib.sha256(Path(IMAGE).read_bytes()).digest(), before)

    def test_saved_settings_survive_reopening_image(self):
        with tempfile.TemporaryDirectory() as state:
            app = Simulator(IMAGE, hidden=True, local_data=True, state_dir=state)
            try:
                app.boot()
                self.assertIn('app', app.scope, app.console.get('1.0', 'end'))
                target = app.scope['app']
                target.tileview.set_tile(target.settings_screen)
                app.invoke(lambda: target.stop_dropdown.select(1))
                # Exercise SAVE through its on-screen hit target.
                app.down(SimpleNamespace(x=100, y=280))
                app.up(SimpleNamespace(x=100, y=280))
                contents = (app.root / 'settings.txt').read_text(encoding='utf-8')
                self.assertEqual(contents.splitlines(), ['Karlskrona Centralstation', 'BUS', 'True'])
                self.assertTrue(app.settings_path().is_file())
            finally:
                app.close()
            reopened = Simulator(IMAGE, hidden=True, local_data=True, state_dir=state)
            try:
                reopened.boot()
                self.assertIn('app', reopened.scope, reopened.console.get('1.0', 'end'))
                target = reopened.scope['app']
                self.assertEqual(target.default_stop, 'Karlskrona Centralstation')
                self.assertEqual(target.stop_dropdown.get_selected(), 1)
                self.assertEqual((reopened.root / 'settings.txt').read_text(encoding='utf-8'), contents)
            finally:
                reopened.close()

    def test_runtime_ticks_imports_and_offline_http(self):
        import sys
        import time
        previous_secrets = sys.modules.get('secrets')
        previous_ticks = getattr(time, 'ticks_ms', None)
        network = Network(True)
        network.station.active(True)
        network.station.connect('test')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'secrets.py').write_text('API_KEY = "test-only"\n', encoding='utf-8')
            (root / 'test_data').mkdir()
            (root / 'test_data' / 'stop_740032188_formatted.json').write_text(
                json.dumps({'stops': [], 'departures': []}), encoding='utf-8')
            with runtime(root, network, local_data=lambda: True):
                import secrets
                import requests
                self.assertEqual(secrets.API_KEY, 'test-only')
                self.assertEqual(time.ticks_diff(time.ticks_add((1 << 30) - 2, 5),
                                                 (1 << 30) - 2), 5)
                self.assertIsInstance(time.ticks_ms(), int)
                with patch.object(requests.real_requests, 'get') as live_get:
                    self.assertEqual(requests.get('https://example.invalid').json()['stops'], [])
                    network.online = False
                    with self.assertRaisesRegex(OSError, 'disconnected'):
                        requests.get('https://example.invalid')
                    live_get.assert_not_called()
                    network.online = True
                    requests.local_data = lambda: False
                    requests.get('https://example.invalid', timeout=10)
                    live_get.assert_called_once_with('https://example.invalid', timeout=10)
            self.assertIs(sys.modules.get('secrets'), previous_secrets)
            self.assertIs(getattr(time, 'ticks_ms', None), previous_ticks)

    def test_reload_preserves_settings_and_runtime_options_before_launch(self):
        with tempfile.TemporaryDirectory() as state:
            app = Simulator(IMAGE, hidden=True, local_data=True, state_dir=state)
            app.boot()
            try:
                self.assertIn('app', app.scope, app.console.get('1.0', 'end'))
                app.invoke(app.scope['app'].save_settings)
                app.online.set(False)
                saved = app.settings_path()

                def launch(command, **kwargs):
                    self.assertTrue(saved.is_file())
                    self.assertIsNone(app.context)
                    self.assertIn('--offline', command)
                    self.assertIn('--local-data', command)
                    self.assertEqual(command[-2:], ['--state-dir', str(Path(state).resolve())])

                with patch('simulator.subprocess.Popen', side_effect=launch) as process:
                    app.reload()
                process.assert_called_once()
            finally:
                if app.context:
                    app.close()

    def test_network_failure(self):
        network = Network(False)
        wlan = network.WLAN()
        wlan.active(True)
        wlan.connect('test', 'test')
        self.assertFalse(wlan.isconnected())
        network.online = True
        self.assertTrue(wlan.isconnected())
        wlan.disconnect()
        self.assertFalse(wlan.isconnected())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image', nargs='?', default=str(DEFAULT_IMAGE))
    IMAGE = parser.parse_args().image
    unittest.main(argv=['test_simulator.py'])
