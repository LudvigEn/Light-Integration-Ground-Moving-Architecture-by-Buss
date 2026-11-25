"""Anchored widgets must draw and receive touches at the same position."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import lvgl_sim as lv
from simulator import Simulator


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.canvas = Mock()
        lv.setup(self.canvas)
        self.addCleanup(lv.teardown, self.canvas)
        draw = patch.object(lv, '_draw_text')
        draw.start()
        self.addCleanup(draw.stop)
        self.app = Simulator.__new__(Simulator)
        self.app.canvas = self.canvas
        self.app.invoke = lambda action: (action(), self.app.refresh())

    def bounds(self, widget):
        self.app.refresh()
        return next(hit[:4] for hit in self.app.hits if hit[-1] is widget)

    def touch(self, x, y):
        event = SimpleNamespace(x=x, y=y)
        self.app.down(event)
        self.app.up(event)

    def test_bottom_keyboard_tracks_resizing_and_parent_movement_with_touch(self):
        panel = lv.obj(lv.screen_active())
        panel.set_pos(30, 20)
        panel.set_size(540, 400)
        field = lv.textarea(panel)
        ready = Mock()
        field.add_event_cb(ready, lv.EVENT.READY, None)
        keys = lv.keyboard(panel)
        # Match the app: alignment is set before the final keyboard size.
        keys.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keys.set_size(400, 180)
        keys.set_map(lv.keyboard.MODE.USER_1, ['q', 'å', '\n', lv.SYMBOL.OK, ''], [1, 1, 1])
        keys.set_mode(lv.keyboard.MODE.USER_1)
        keys.set_textarea(field)

        self.assertEqual(self.bounds(keys), (100, 240, 500, 420))
        self.touch(400, 285)
        self.assertEqual(field.get_text(), 'å')
        self.touch(300, 375)
        ready.assert_called_once()

        panel.set_pos(20, 10)
        panel.set_size(500, 360)
        keys.set_size(300, 140)
        self.assertEqual(self.bounds(keys), (120, 230, 420, 370))
        self.touch(345, 265)
        self.assertEqual(field.get_text(), 'åå')
        self.touch(270, 335)
        self.assertEqual(ready.call_count, 2)

    def test_keyboard_default_anchor_and_position_offsets_match_device(self):
        keys = lv.keyboard(lv.screen_active())
        keys.set_size(600, 240)
        self.assertEqual(self.bounds(keys), (0, 210, 600, 450))
        keys.set_pos(0, 210)
        self.assertEqual(self.bounds(keys), (0, 420, 600, 450))
        keys.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.assertEqual(self.bounds(keys), (0, 210, 600, 450))

    def test_application_search_popup_aligns_keys_and_confirms_stop(self):
        # Exercise the actual saved app method without hardware or credentials.
        source = Path(__file__).resolve().parents[1] / 'project' / 'main.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        application = next(node for node in tree.body
                           if isinstance(node, ast.ClassDef) and node.name == 'Application')
        namespace = {'lv': lv, 'log': lambda _message: None}
        exec(compile(ast.Module(body=[application], type_ignores=[]), str(source), 'exec'), namespace)
        target = namespace['Application'].__new__(namespace['Application'])
        target.font_16 = lv.font_montserrat_16
        control = lv.dropdown(lv.screen_active())
        control.set_options('Alpha\nBergåsa\nCampus Gräsvik')
        changed = Mock()
        control.add_event_cb(changed, lv.EVENT.VALUE_CHANGED, None)
        target.open_search(control)
        panel = lv.screen_active().children[-1]
        field = next(child for child in panel.children if isinstance(child, lv.textarea))
        keys = next(child for child in panel.children if isinstance(child, lv.keyboard))
        results = next(child for child in panel.children if isinstance(child, lv.dropdown))

        self.assertEqual(self.bounds(keys), (0, 210, 600, 450))
        self.touch(573, 240)  # Swedish å key on the first row.
        self.assertEqual(field.get_text(), 'å')
        self.assertEqual(results.get_options(), 'Bergåsa')
        self.touch(563, 420)  # Confirm using the visible OK key.
        self.assertEqual(control.get_selected(), 1)
        self.assertNotIn(panel, lv.screen_active().children)
        self.assertIsNone(keys.get_textarea())
        changed.assert_called_once()

    def test_supported_anchors_and_center_reset_offsets(self):
        panel = lv.obj(lv.screen_active())
        panel.set_pos(20, 30)
        panel.set_size(300, 200)
        child = lv.obj(panel)
        child.set_size(80, 40)
        for alignment, bounds in (
                (lv.ALIGN.TOP_LEFT, (30, 35, 110, 75)),
                (lv.ALIGN.TOP_MID, (140, 35, 220, 75)),
                (lv.ALIGN.CENTER, (140, 115, 220, 155)),
                (lv.ALIGN.BOTTOM_MID, (140, 195, 220, 230))):
            with self.subTest(alignment=alignment):
                child.align(alignment, 10, 5)
                self.assertEqual(self.bounds(child), bounds)
        child.center()
        self.assertEqual(self.bounds(child), (130, 110, 210, 150))
        with self.assertRaises(NotImplementedError):
            child.align(-1)


if __name__ == '__main__':
    unittest.main()
