"""LVGL invalidation and immediate refresh must only redraw existing widgets."""
import unittest
from unittest.mock import Mock, patch

import lvgl_sim as lv


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.canvas = Mock()
        self.screen = lv.setup(self.canvas)
        self.addCleanup(lv.teardown, self.canvas)
        context = lv.timer_context()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def test_invalidate_defers_redraw_and_timer_handler_flushes_it(self):
        callback = Mock()
        child = lv.obj(self.screen)
        child.set_pos(12, 34)
        child.add_event_cb(callback, lv.EVENT.ALL, None)
        with patch.object(lv, 'render') as render:
            self.screen.invalidate()
            render.assert_not_called()
            self.assertTrue(lv._refresh_pending)
            self.assertEqual(child.get_parent(), self.screen)
            self.assertEqual((child.x, child.y), (12, 34))
            lv.timer_handler()
            render.assert_called_once_with()
            self.assertFalse(lv._refresh_pending)
        callback.assert_not_called()
        self.assertEqual(self.screen.children, [child])

    def test_immediate_refresh_uses_host_callback_without_running_timers(self):
        host_refresh, timer_callback = Mock(), Mock()
        lv.setup(self.canvas, on_refresh=host_refresh)
        lv.timer_create(timer_callback, 0, None)
        with patch.object(lv, 'render') as render:
            lv.refr_now(None)
            host_refresh.assert_called_once_with()
            render.assert_not_called()
        timer_callback.assert_not_called()
        self.canvas.update_idletasks.assert_called_once_with()

    def test_invalidation_of_hidden_inactive_and_detached_objects_is_ignored(self):
        view = lv.tileview(self.screen)
        active = view.add_tile(0, 0, lv.DIR.RIGHT)
        inactive = view.add_tile(1, 0, lv.DIR.LEFT)
        inactive.invalidate()
        self.assertFalse(lv._refresh_pending)
        hidden = lv.obj(active)
        child = lv.obj(hidden)
        hidden.add_flag(lv.obj.FLAG.HIDDEN)
        child.invalidate()
        self.assertFalse(lv._refresh_pending)
        lv.obj().invalidate()
        self.assertFalse(lv._refresh_pending)
        active.invalidate()
        self.assertTrue(lv._refresh_pending)

    def test_refresh_failure_releases_reentry_guard_and_rejects_other_displays(self):
        with self.assertRaises(NotImplementedError):
            lv.refr_now(object())
        with patch.object(lv, 'render', side_effect=ValueError('draw failed')):
            with self.assertRaisesRegex(ValueError, 'draw failed'):
                lv.refr_now(None)
        self.assertFalse(lv._refreshing)
        with patch.object(lv, 'render') as render:
            lv.refr_now(None)
            render.assert_called_once()

    def test_closed_canvas_does_not_keep_refresh_callbacks(self):
        self.screen.invalidate()
        lv.teardown(self.canvas)
        self.assertFalse(lv._refresh_pending)
        with self.assertRaisesRegex(RuntimeError, 'No simulated display'):
            lv.refr_now(None)


if __name__ == '__main__':
    unittest.main()
