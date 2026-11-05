"""Timer semantics and Tk countdown updates without waiting a real minute."""
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import lvgl_sim as lv
from simulator import Simulator, runtime
from timer_sim import NO_TIMER_READY, TimerManager


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.manager = TimerManager(clock=lambda: self.now)

    def test_callback_period_user_data_and_no_catchup_burst(self):
        calls = []
        data = object()
        timer = self.manager.create(lambda current: calls.append(current.get_user_data()), 1000, data)
        self.now = 999
        self.assertEqual(self.manager.run_due(), 0)
        self.assertEqual(self.manager.next_delay(), 1)
        self.now = 1000
        self.assertEqual(self.manager.run_due(), 1)
        self.assertEqual(calls, [data])
        self.now = 100_000
        self.manager.run_due()
        self.assertEqual(calls, [data, data])
        self.manager.run_due()
        self.assertEqual(len(calls), 2)
        self.assertEqual(timer.get_period(), 1000)

    def test_pause_resume_ready_reset_and_period_changes(self):
        callback = Mock()
        timer = self.manager.create(callback, 1000, None)
        timer.pause()
        self.now = 5000
        self.assertEqual(self.manager.next_delay(), NO_TIMER_READY)
        self.manager.run_due()
        callback.assert_not_called()
        timer.resume()
        self.manager.run_due()
        callback.assert_called_once_with(timer)
        timer.ready()
        self.manager.run_due()
        self.assertEqual(callback.call_count, 2)
        timer.ready()
        timer.reset()
        self.manager.run_due()
        self.assertEqual(callback.call_count, 2)
        timer.set_period(500)
        self.now += 499
        self.manager.run_due()
        self.assertEqual(callback.call_count, 2)
        self.now += 1
        self.manager.run_due()
        self.assertEqual(callback.call_count, 3)

    def test_repeat_count_auto_delete_and_reusable_timer(self):
        counts = []
        timer = self.manager.create(lambda current: counts.append(current.repeat_count), 100, None)
        timer.set_repeat_count(2)
        self.now = 100
        self.manager.run_due()
        self.assertEqual(counts, [1])
        self.now = 200
        self.manager.run_due()
        self.assertEqual(counts, [1, 0])
        self.assertTrue(timer.deleted)
        callback = Mock()
        timer = self.manager.create(callback, 100, None)
        timer.set_repeat_count(1)
        timer.set_auto_delete(False)
        self.now = 300
        self.manager.run_due()
        self.assertTrue(timer.get_paused())
        self.assertFalse(timer.deleted)
        timer.set_repeat_count(1)
        timer.reset()
        timer.resume()
        self.now = 400
        self.manager.run_due()
        self.assertEqual(callback.call_count, 2)

    def test_callbacks_can_delete_create_and_reenter_safely(self):
        calls = []
        victim = self.manager.create(lambda timer: calls.append('victim'), 0, None)
        def first_callback(timer):
            victim.delete()
            self.assertEqual(self.manager.run_due(), 0)
            self.manager.create(lambda current: calls.append('new'), 0, None)
            calls.append('first')
            timer.delete()
        self.manager.create(first_callback, 0, None)
        self.manager.run_due()
        self.assertEqual(calls, ['first'])
        self.manager.run_due()
        self.assertEqual(calls, ['first', 'new'])

    def test_exception_pauses_broken_timer_and_other_timers_continue(self):
        good, errors = Mock(), Mock()
        self.manager.create(good, 0, None)
        bad = self.manager.create(Mock(side_effect=RuntimeError('broken timer')), 0, None)
        self.assertEqual(self.manager.run_due(errors), 2)
        good.assert_called_once()
        errors.assert_called_once()
        self.assertTrue(bad.paused)
        self.manager.run_due(errors)
        errors.assert_called_once()

    def test_validation_global_enable_and_deleted_timer(self):
        for period in (-1, 1.5, 1 << 32):
            with self.assertRaises(ValueError):
                self.manager.create(None, period, None)
        with self.assertRaises(TypeError):
            self.manager.create('not callable', 1000, None)
        callback = Mock()
        timer = self.manager.create(callback, 0, None)
        self.manager.enabled = False
        self.manager.run_due()
        callback.assert_not_called()
        self.manager.enabled = True
        self.manager.run_due()
        callback.assert_called_once()
        timer.delete()
        with self.assertRaisesRegex(ValueError, 'deleted'):
            timer.reset()

    def test_lvgl_aliases_and_context_cleanup(self):
        callback = Mock()
        with lv.timer_context():
            timer = lv.timer_create_basic()
            lv.timer_set_cb(timer, callback)
            lv.timer_set_period(timer, 1000)
            lv.timer_set_user_data(timer, 'data')
            self.assertEqual(lv.timer_get_user_data(timer), 'data')
            lv.timer_pause(timer)
            lv.timer_ready(timer)
            lv.timer_handler()
            callback.assert_not_called()
            lv.timer_resume(timer)
            lv.timer_enable(False)
            lv.timer_handler()
            callback.assert_not_called()
            lv.timer_enable(True)
            lv.timer_handler()
            callback.assert_called_once_with(timer)
            with lv.timer_context():
                inner = lv.timer_create(None, 0, None)
            self.assertTrue(inner.deleted)
            self.assertFalse(timer.deleted)
        self.assertTrue(timer.deleted)


class TimerLoopTests(unittest.TestCase):
    def setUp(self):
        self.now = 100_000
        clock_patch = patch('time.monotonic', side_effect=lambda: self.now / 1000)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        self.app = Simulator(hidden=True, state_dir=state.name)
        self.addCleanup(self.app.close)
        self.app.context = runtime(self.app.root, self.app.network, lambda: True)
        self.app.context.__enter__()

    def pump(self):
        self.app._stop_timer_pump()
        self.app._timer_after = self.app.window.after(0, self.app._pump_timers)
        self.app.window.update()

    def test_countdown_updates_canvas_and_refreshes_once_at_sixty_seconds(self):
        caption = lv.label(lv.screen_active())
        caption.set_text('60')
        state = SimpleNamespace(start=time.ticks_ms(), refreshes=0)
        def countdown(timer):
            self.assertIs(timer.get_user_data(), caption)
            elapsed = time.ticks_diff(time.ticks_ms(), state.start)
            seconds = (max(0, 60_000 - elapsed) + 999) // 1000
            caption.set_text(str(seconds))
            if seconds == 0:
                state.refreshes += 1
                state.start = time.ticks_ms()
                caption.set_text('60')
        timer = lv.timer_create(countdown, 1000, caption)
        self.app._start_timer_pump()
        self.now += 59_000
        self.pump()
        self.assertEqual(caption.get_text(), '1')
        texts = [self.app.canvas.itemcget(item, 'text') for item in self.app.canvas.find_all()
                 if self.app.canvas.type(item) == 'text']
        self.assertIn('1', texts)
        self.now += 1000
        self.pump()
        self.assertEqual(state.refreshes, 1)
        self.assertEqual(caption.get_text(), '60')
        self.pump()
        self.assertEqual(state.refreshes, 1)
        self.app.close()
        self.assertTrue(timer.deleted)
        self.assertIsNone(self.app._timer_after)

    def test_ticks_wraparound_and_no_redraw_when_idle(self):
        self.now += (1 << 30) - 500
        started = time.ticks_ms()
        values = []
        lv.timer_create(lambda timer: values.append(time.ticks_diff(time.ticks_ms(), started)), 1000, None)
        with patch.object(self.app, 'refresh', wraps=self.app.refresh) as refresh:
            self.pump()
            refresh.assert_not_called()
            self.now += 1000
            self.pump()
            self.assertEqual(values, [1000])
            refresh.assert_called_once()

    def test_boot_starts_application_timers_automatically(self):
        self.app.context.__exit__(None, None, None)
        self.app.context = None
        (self.app.root / 'main.py').write_text(
            'import lvgl as lv\n'
            'label = lv.label(lv.screen_active())\n'
            'label.set_text("0")\n'
            'def tick(timer):\n'
            '    label.set_text(str(int(label.get_text()) + 1))\n'
            'timer = lv.timer_create(tick, 1000, None)\n', encoding='utf-8')
        self.app.source = self.app.root / 'timer-test.img'
        with patch('simulator.extract_image', side_effect=lambda source, destination: source):
            self.app.boot()
        self.assertIn('label', self.app.scope, self.app.console.get('1.0', 'end'))
        self.assertIsNotNone(self.app._timer_after)
        self.now += 1000
        self.pump()
        self.assertEqual(self.app.scope['label'].get_text(), '1')

    def test_timer_errors_reach_console_and_timers_stop_on_close(self):
        bad = lv.timer_create(Mock(side_effect=RuntimeError('countdown failed')), 0, None)
        good = Mock()
        lv.timer_create(good, 0, None)
        self.pump()
        self.assertIn('countdown failed', self.app.console.get('1.0', 'end'))
        self.assertIn('timer callback failed', self.app.status.get())
        self.assertTrue(bad.paused)
        good.assert_called()
        self.app.close()
        count = good.call_count
        lv.timer_handler()
        self.assertEqual(good.call_count, count)


if __name__ == '__main__':
    unittest.main()
