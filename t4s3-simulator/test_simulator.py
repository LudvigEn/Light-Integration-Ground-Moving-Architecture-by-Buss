"""Integration checks: real image extraction, boot, touch callbacks, reset state."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from fat_image import FatImage
from simulator import Simulator, Network

IMAGE = None


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
        app = Simulator(IMAGE, hidden=True)
        try:
            app.boot()
            self.assertIn('app', app.scope, app.console.get('1.0', 'end'))
            target = app.scope['app']
            self.assertEqual(target.tileview.active, (0, 0))
            app.down(SimpleNamespace(x=500, y=200))
            app.up(SimpleNamespace(x=100, y=200))
            self.assertEqual(target.tileview.active, (1, 0))
            app.down(SimpleNamespace(x=300, y=225))
            app.up(SimpleNamespace(x=300, y=225))
            self.assertTrue(target.tile2_dark)
            self.assertEqual(target.tile2.bg, '#000000')
            self.assertEqual(target.tile2_label.fg, '#ffffff')
            app.down(SimpleNamespace(x=300, y=225))
            app.up(SimpleNamespace(x=300, y=225))
            self.assertFalse(target.tile2_dark)
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
    parser.add_argument('image')
    IMAGE = parser.parse_args().image
    unittest.main(argv=['test_simulator.py'])
