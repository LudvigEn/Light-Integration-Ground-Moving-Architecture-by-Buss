"""Integration checks: real image extraction, boot, touch callbacks, reset state."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fat_image import FatImage
from simulator import Simulator, Network, DEFAULT_IMAGE
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
        app = Simulator(source, hidden=True)
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
            app.down(SimpleNamespace(x=275, y=90))
            app.up(SimpleNamespace(x=275, y=90))
            self.assertFalse(target.dark_mode)
            self.assertEqual(target.settings_screen.bg, '#ffffff')
            self.assertTrue(all(label.fg == '#000000' for label in target.labels))
            app.down(SimpleNamespace(x=275, y=90))
            app.up(SimpleNamespace(x=275, y=90))
            self.assertTrue(target.dark_mode)
            self.assertEqual(target.settings_screen.bg, '#000000')
            self.assertTrue(all(label.fg == '#ffffff' for label in target.labels))
            app.move(1, 0)
            self.assertEqual(target.tileview.active, (2, 0))
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
