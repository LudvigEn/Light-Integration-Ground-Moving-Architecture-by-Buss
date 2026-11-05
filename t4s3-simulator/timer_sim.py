"""Cooperative LVGL timers, driven by the simulator's Tk event loop."""
import math
import time


NO_TIMER_READY = 0xFFFFFFFF


class Timer:
    """LVGL timer methods. Callbacks receive this object, not its user data."""

    def __init__(self, manager, callback, period, user_data):
        self.manager = manager
        self.deleted = False
        self.paused = False
        self.repeat_count = -1
        self.auto_delete = True
        self.set_cb(callback)
        self.set_period(period)
        self.user_data = user_data
        self.reset()

    def _check_alive(self):
        if self.deleted:
            raise ValueError('Timer has been deleted')

    def set_cb(self, callback):
        self._check_alive()
        if callback is not None and not callable(callback):
            raise TypeError('Timer callback must be callable or None')
        self.callback = callback

    def set_period(self, period):
        self._check_alive()
        if not isinstance(period, int) or not 0 <= period <= 0xFFFFFFFF:
            raise ValueError('Timer period must be a nonnegative integer in milliseconds')
        self.period = period

    def get_period(self):
        self._check_alive()
        return self.period

    def set_user_data(self, user_data):
        self._check_alive()
        self.user_data = user_data

    def get_user_data(self):
        self._check_alive()
        return self.user_data

    def set_repeat_count(self, count):
        self._check_alive()
        if not isinstance(count, int) or count < -1:
            raise ValueError('Timer repeat count must be -1 or a nonnegative integer')
        self.repeat_count = count

    def set_auto_delete(self, enabled):
        self._check_alive()
        self.auto_delete = bool(enabled)

    def pause(self):
        self._check_alive()
        self.paused = True

    def resume(self):
        self._check_alive()
        self.paused = False

    def get_paused(self):
        self._check_alive()
        return self.paused

    def reset(self):
        self._check_alive()
        self.last_run = self.manager.clock()
        self._ready = False

    def ready(self):
        self._check_alive()
        self._ready = True

    def delete(self):
        if not self.deleted:
            self.deleted = True
            self.manager.timers.remove(self)
            self.callback = self.user_data = None

    def _remaining(self, now):
        return 0 if self._ready else max(0, math.ceil(self.last_run + self.period - now))


class TimerManager:
    def __init__(self, clock=None):
        self.clock = clock or (lambda: time.monotonic() * 1000)
        self.timers = []
        self.enabled = True
        self.running = False

    def create(self, callback, period, user_data):
        timer = Timer(self, callback, period, user_data)
        self.timers.insert(0, timer)
        return timer

    def clear(self):
        for timer in self.timers[:]:
            timer.delete()

    def next_delay(self):
        if not self.enabled:
            return NO_TIMER_READY
        now = self.clock()
        return min((timer._remaining(now) for timer in self.timers if not timer.paused),
                   default=NO_TIMER_READY)

    def run_due(self, on_error=None):
        if self.running or not self.enabled:
            return 0
        self.running = True
        executed = 0
        try:
            # A snapshot permits callbacks to delete/pause other timers or
            # create new ones. Newly created timers start on the next pass.
            for timer in self.timers[:]:
                if not self.enabled:
                    break
                if timer.deleted or timer.paused or timer._remaining(self.clock()):
                    continue
                original_count = timer.repeat_count
                if timer.repeat_count > 0:
                    timer.repeat_count -= 1
                timer.reset()
                try:
                    if original_count != 0 and timer.callback is not None:
                        executed += 1
                        timer.callback(timer)
                except Exception as error:
                    # Report once instead of repeating a broken callback.
                    if not timer.deleted:
                        timer.pause()
                    if on_error is None:
                        raise
                    on_error(error)
                finally:
                    if not timer.deleted and timer.repeat_count == 0:
                        if timer.auto_delete:
                            timer.delete()
                        else:
                            timer.pause()
        finally:
            self.running = False
        return executed
