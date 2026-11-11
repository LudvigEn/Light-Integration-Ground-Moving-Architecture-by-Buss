"""MicroPython fs_driver interface for the simulator's extracted filesystem."""


def fs_register(fs_drv, letter, cache_size=500):
    """Register a drive letter using the current simulated filesystem root."""
    if not isinstance(letter, str) or len(letter) != 1:
        raise ValueError('LVGL filesystem drive must be one ASCII letter')
    fs_drv.init()
    fs_drv.letter = ord(letter)
    if cache_size >= 0:
        fs_drv.cache_size = cache_size
    fs_drv.register()
