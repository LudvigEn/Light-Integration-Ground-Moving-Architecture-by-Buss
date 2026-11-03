"""Integration checks: real image extraction, boot, touch callbacks, reset state."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fat_image import FatImage
from simulator import Simulator, Network, DEFAULT_IMAGE, runtime
import lvgl_sim as lv

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
        self.assertEqual(choose.call_args.kwargs['initialfile'], 't4s3-vfs-deploy.img')
        self.app.restart.assert_not_called()


class SimulatorTests(unittest.TestCase):
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
