"""Touch, keyboard and selection-state checks for searchable stop selectors."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tkinter as tk

import lvgl_sim as lv
from search_dropdown import add_dropdown_search
from simulator import Simulator


class TextInputTests(unittest.TestCase):
    def setUp(self):
        lv.setup(Mock())
        self.field = lv.textarea(lv.screen_active())
        self.field.set_one_line(True)
        self.keyboard = lv.keyboard(lv.screen_active())
        self.keyboard.set_textarea(self.field)

    def test_unicode_editing_and_cursor_changes_emit_one_event_per_edit(self):
        changes = []
        self.field.add_event_cb(lambda event: changes.append(event.get_target().get_text()),
                                lv.EVENT.VALUE_CHANGED, None)
        self.field.set_text('Åö')
        self.keyboard.press_key(lv.SYMBOL.LEFT)
        self.keyboard.press_key('ä')
        self.keyboard.press_key(lv.SYMBOL.BACKSPACE)
        self.field.delete_char_forward()
        self.assertEqual(changes, ['Åö', 'Åäö', 'Åö', 'Å'])
        self.assertEqual(self.field.get_cursor_pos(), 1)

    def test_limits_one_line_and_accepted_characters(self):
        self.field.set_max_length(3)
        self.field.set_accepted_chars('åäö')
        self.field.add_text('å\nAäöå')
        self.assertEqual(self.field.get_text(), 'åäö')
        self.field.set_cursor_pos(0)
        self.field.add_text('ä')
        self.assertEqual(self.field.get_text(), 'åäö')

    def test_touch_keyboard_ready_cancel_and_mode_switches(self):
        events = []
        self.field.add_event_cb(lambda event: events.append(event.get_code()), lv.EVENT.ALL, None)
        self.keyboard.press_key('abc')
        self.assertEqual(self.keyboard.get_mode(), lv.keyboard.MODE.TEXT_LOWER)
        self.keyboard.press_key(lv.SYMBOL.OK)
        self.keyboard.press_key(lv.SYMBOL.CLOSE)
        self.assertEqual(events, [lv.EVENT.READY, lv.EVENT.CANCEL])
        self.keyboard.add_state(lv.STATE.DISABLED)
        self.keyboard.press_key('x')
        self.assertEqual(self.field.get_text(), '')

    def test_desktop_editing_is_consumed_but_hidden_deleted_fields_are_not(self):
        self.assertTrue(lv.handle_key('a', 'å'))
        lv.handle_key('Left')
        lv.handle_key('x', 'x')
        self.assertEqual(self.field.get_text(), 'xå')
        self.field.add_flag(lv.obj.FLAG.HIDDEN)
        self.assertFalse(lv.handle_key('y', 'y'))
        self.field.remove_flag(lv.obj.FLAG.HIDDEN)
        self.field.delete()
        self.assertFalse(lv.handle_key('z', 'z'))

    def test_focus_moves_between_fields_and_detaches_on_parent_deletion(self):
        events = []
        self.field.add_event_cb(lambda event: events.append(event.get_code()), lv.EVENT.ALL, None)
        other = lv.textarea(lv.screen_active())
        other.click()
        lv.handle_key('x', 'x')
        self.assertEqual(other.get_text(), 'x')
        self.assertEqual(self.field.get_text(), '')
        self.assertIn(lv.EVENT.DEFOCUSED, events)
        lv.screen_active().clean()
        self.assertFalse(lv.handle_key('x', 'x'))


class SearchDropdownTests(unittest.TestCase):
    def setUp(self):
        self.draw = patch.object(lv, '_draw_text')
        self.draw.start()
        self.addCleanup(self.draw.stop)
        self.canvas = Mock()
        lv.setup(self.canvas)
        self.view = lv.tileview(lv.screen_active())
        self.view.set_size(600, 450)
        self.tile = self.view.add_tile(0, 0, lv.DIR.RIGHT)
        self.view.add_tile(1, 0, lv.DIR.LEFT)
        self.app = Simulator.__new__(Simulator)
        self.app.canvas = self.canvas
        self.app.source = None
        self.app.invoke = lambda action: (action(), self.app.refresh())
        self.controls = []
        self.changes = []
        self.names = ['Alpha', 'Bergåsa', 'Campus Gräsvik', 'Östra']
        for row in range(3):
            control = lv.dropdown(self.tile)
            control.set_pos(110, 50 + 50 * row)
            control.set_options('\n'.join(self.names))
            control.set_selected(2)
            control.add_event_cb(lambda event, row=row: self.changes.append(
                (row, event.get_target().get_selected())), lv.EVENT.VALUE_CHANGED, None)
            trigger = add_dropdown_search(self.tile, control, lv.font_montserrat_16, 280, 50 + 50 * row)
            self.controls.append((control, trigger))
        self.app.refresh()

    def touch(self, x, y):
        event = SimpleNamespace(x=x, y=y)
        self.app.down(event)
        self.app.up(event)

    def open(self, row=0):
        self.touch(300, 70 + 50 * row)
        panel = lv.screen_active().children[-1]
        field = next(child for child in panel.children if isinstance(child, lv.textarea))
        keys = next(child for child in panel.children if isinstance(child, lv.keyboard))
        results = next(child for child in panel.children if isinstance(child, lv.dropdown))
        return panel, field, keys, results

    def test_all_three_selectors_confirm_using_original_option_indexes(self):
        for row in range(3):
            _panel, field, keys, results = self.open(row)
            field.set_text('ÖS')
            self.assertEqual(results.get_options(), 'Östra')
            self.assertEqual(self.controls[row][0].get_selected(), 2)
            keys.press_key(lv.SYMBOL.OK)
            self.assertEqual(self.controls[row][0].get_selected(), 3)
            self.app.refresh()
        self.assertEqual(self.changes, [(0, 3), (1, 3), (2, 3)])

    def test_touch_types_swedish_letters_and_picking_result_confirms(self):
        _panel, field, keys, results = self.open()
        # Row one has eleven equal-width keys; å is the final one.
        self.touch(573, 240)
        self.assertEqual(field.get_text(), 'å')
        self.assertEqual(results.get_options(), 'Bergåsa')
        self.touch(100, 100)
        self.assertTrue(results.is_open())
        self.touch(100, 135)
        self.assertFalse(results.is_open())
        # Tick is the last key in the final row (weights 1, 1, 4, 1, 1).
        self.touch(563, 420)
        self.assertEqual(self.controls[0][0].get_selected(), 1)
        self.assertEqual(self.changes, [(0, 1)])
        self.assertIsNone(keys.get_textarea())

    def test_no_matches_cannot_commit_and_cancel_preserves_original(self):
        panel, field, keys, results = self.open()
        field.set_text('nowhere')
        self.assertTrue(results.has_state(lv.STATE.DISABLED))
        keys.press_key(lv.SYMBOL.OK)
        self.assertIn(panel, lv.screen_active().children)
        keys.press_key(lv.SYMBOL.CLOSE)
        self.assertNotIn(panel, lv.screen_active().children)
        self.assertEqual(self.controls[0][0].get_selected(), 2)
        self.assertEqual(self.changes, [])
        self.assertIsNone(lv._focused_textarea)

    def test_reopening_reads_updated_options_and_clears_search(self):
        _panel, field, keys, _results = self.open()
        field.set_text('Berg')
        keys.press_key(lv.SYMBOL.CLOSE)
        control = self.controls[0][0]
        control.set_options('New transport stop\nAnother')
        self.app.refresh()
        _panel, field, _keys, results = self.open()
        self.assertEqual(field.get_text(), '')
        self.assertEqual(results.get_options(), control.get_options())

    def test_desktop_arrows_edit_instead_of_navigating_and_modal_blocks_swipes(self):
        _panel, field, _keys, _results = self.open()
        field.set_text('AB')
        self.assertEqual(self.app.key(SimpleNamespace(keysym='Left', char='')), 'break')
        self.app.key(SimpleNamespace(keysym='x', char='x'))
        self.assertEqual(field.get_text(), 'AxB')
        self.app.down(SimpleNamespace(x=500, y=185))
        self.app.up(SimpleNamespace(x=100, y=185))
        self.assertEqual(self.view.active, (0, 0))

    def test_long_results_scroll_within_keyboard_free_area(self):
        control = self.controls[0][0]
        control.set_options('\n'.join('Stop %03d' % index for index in range(150)))
        _panel, _field, keys, results = self.open()
        self.touch(100, 100)
        popup = results.get_list()
        keyboard_top = next(hit[1] for hit in self.app.hits if hit[-1] is keys)
        self.assertLessEqual(popup.y + popup.height, keyboard_top)
        self.app.wheel(SimpleNamespace(x=100, y=135), delta=10000)
        self.touch(100, popup.y + popup.height - 10)
        keys.press_key(lv.SYMBOL.OK)
        self.assertEqual(control.get_selected(), 149)


class TextInputRenderingTests(unittest.TestCase):
    def test_real_canvas_draws_custom_font_keys_and_text_then_cleans_up(self):
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        canvas = tk.Canvas(window, width=600, height=450)
        lv.setup(canvas)
        root = Path(__file__).resolve().parents[1]
        font = lv.binfont_create_from_buffer((root / 'project/fonts/transit_16.bin').read_bytes())
        font.fallback = lv.font_montserrat_16
        control = lv.dropdown(lv.screen_active())
        control.set_options('Bergåsa\nÖstra')
        trigger = add_dropdown_search(lv.screen_active(), control, font, 300, 100)
        trigger.click()
        panel = lv.screen_active().children[-1]
        field = next(child for child in panel.children if isinstance(child, lv.textarea))
        keys = next(child for child in panel.children if isinstance(child, lv.keyboard))
        field.add_text('å')
        hits = lv.render()
        self.assertTrue(field._text_images)
        self.assertTrue(any(slot.startswith('key') for slot in keys._text_images))
        self.assertTrue(any(node.parent is keys for *_bounds, node in hits))
        self.assertTrue(any(canvas.type(item) == 'line' for item in canvas.find_all()))
        keys.press_key(lv.SYMBOL.CLOSE)
        lv.render()
        self.assertEqual(len(lv.screen_active().children), 2)
        self.assertIsNone(lv._focused_textarea)


if __name__ == '__main__':
    unittest.main()
