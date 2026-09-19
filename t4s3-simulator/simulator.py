"""Desktop application simulator for the course LilyGO T4-S3 image."""
import argparse
import builtins
import contextlib
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import traceback
import tkinter as tk
from tkinter import filedialog, ttk
from types import ModuleType

from fat_image import FatImage
import lvgl_sim as lv

DEFAULT_IMAGE = Path(__file__).resolve().parent.parent / 'device-build' / 't4s3-vfs-deploy.img'


class Network(ModuleType):
    STA_IF = 0
    AP_IF = 1

    def __init__(self, online):
        super().__init__('network')
        self.online = online
        self.station = self.Station(self)

    def WLAN(self, interface=0):
        if interface != self.STA_IF:
            raise NotImplementedError('Only station Wi-Fi is simulated')
        return self.station

    class Station:
        def __init__(self, network):
            self.network = network
            self.enabled = False
            self.connected = False

        def active(self, value=None):
            if value is not None:
                self.enabled = bool(value)
                if not value:
                    self.connected = False
            return self.enabled

        def connect(self, ssid, password=None):
            self.connected = self.enabled

        def disconnect(self):
            self.connected = False

        def isconnected(self):
            return self.enabled and self.connected and self.network.online

        def status(self):
            return 3 if self.isconnected() else 0

        def ifconfig(self):
            return ('192.0.2.2', '255.255.255.0', '192.0.2.1', '192.0.2.1')


@contextlib.contextmanager
def runtime(root, network):
    """Compatibility for trusted application code. This is NOT a security sandbox."""
    original_open, original_listdir = builtins.open, os.listdir
    original_cwd = Path.cwd()
    original_path = sys.path[:]
    modules = {name: sys.modules.get(name) for name in ('lvgl', 'network', 'board_lvgl', 'utime', 'uos')}
    time_names = ('ticks_ms', 'ticks_us', 'ticks_diff', 'ticks_add', 'sleep_ms', 'sleep_us')
    old_time = {name: getattr(time, name, None) for name in time_names}
    old_exception = getattr(sys, 'print_exception', None)
    board = ModuleType('board_lvgl')
    board.start_board = lambda: (None, None, None)
    sys.modules.update(lvgl=lv, network=network, board_lvgl=board, utime=time, uos=os)
    start = time.monotonic()
    time.ticks_ms = lambda: int((time.monotonic() - start) * 1000) % (1 << 30)
    time.ticks_us = lambda: int((time.monotonic() - start) * 1000000) % (1 << 30)
    time.ticks_diff = lambda a, b: ((a - b + (1 << 29)) % (1 << 30)) - (1 << 29)
    time.ticks_add = lambda a, b: (a + b) % (1 << 30)
    time.sleep_ms = lambda ms: time.sleep(ms / 1000)
    time.sleep_us = lambda us: time.sleep(us / 1000000)
    sys.print_exception = lambda error, stream=None: traceback.print_exception(type(error), error, error.__traceback__, file=stream or sys.stdout)

    def device_path(path):
        if isinstance(path, (str, os.PathLike)):
            path = os.fspath(path)
            if path.startswith('/'):
                path = str(root / path.lstrip('/'))
        return path

    builtins.open = lambda path, *a, **kw: original_open(device_path(path), *a, **kw)
    os.listdir = lambda path='.': original_listdir(device_path(path))
    os.chdir(root)
    sys.path.insert(0, str(root))
    try:
        yield
    finally:
        builtins.open, os.listdir = original_open, original_listdir
        os.chdir(original_cwd)
        sys.path[:] = original_path
        for name, previous in modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        for name, previous in old_time.items():
            if previous is None:
                delattr(time, name)
            else:
                setattr(time, name, previous)
        if old_exception is None:
            del sys.print_exception
        else:
            sys.print_exception = old_exception


class Simulator:
    def __init__(self, source=None, offline=False, hidden=False):
        self.source = (Path(source).resolve() if source else
                       DEFAULT_IMAGE if DEFAULT_IMAGE.is_file() else None)
        self.window = tk.Tk()
        self.window.title('LilyGO T4-S3 • Python application simulator')
        self.window.resizable(False, False)
        if hidden:
            self.window.withdraw()
        self.network = Network(not offline)
        self.temp = tempfile.TemporaryDirectory(prefix='t4s3-sim-')
        self.root = Path(self.temp.name)
        self.context = None
        self.scope = {}
        self.hits = []
        self.press = (0, 0)
        self.drag_mode = None
        self.drag_tile = None
        self.drag_scroll_y = 0
        toolbar = ttk.Frame(self.window, padding=8)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Open image…', command=self.choose).pack(side='left')
        ttk.Button(toolbar, text='Reset / Reload', command=self.reload).pack(side='left', padx=6)
        self.online = tk.BooleanVar(value=not offline)
        ttk.Checkbutton(toolbar, text='Simulated Wi-Fi', variable=self.online,
                        command=lambda: setattr(self.network, 'online', self.online.get())).pack(side='left')
        self.canvas = tk.Canvas(self.window, width=600, height=450, highlightthickness=0, bg='black')
        self.canvas.pack(padx=16, pady=8)
        lv.setup(self.canvas)
        ttk.Label(self.window, text='Swipe sideways for tiles • Drag vertically or wheel to scroll • Click to touch').pack()
        self.status = tk.StringVar(value='Open a FAT filesystem .img to run its main.py')
        ttk.Label(self.window, textvariable=self.status, wraplength=600).pack(padx=12, pady=6)
        self.console = tk.Text(self.window, height=9, width=82, bg='#17212b', fg='#e5eef6', state='disabled')
        self.console.pack(padx=12, pady=(0, 12))
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-4>', lambda event: self.wheel(event, -60))
        self.canvas.bind('<Button-5>', lambda event: self.wheel(event, 60))
        for key, delta in [('Left', (-1, 0)), ('Right', (1, 0)), ('Up', (0, -1)), ('Down', (0, 1))]:
            self.window.bind('<' + key + '>', lambda event, d=delta: self.move(*d))
        self.window.protocol('WM_DELETE_WINDOW', self.close)

    def write(self, text):
        self.console.configure(state='normal')
        self.console.insert('end', text)
        self.console.see('end')
        self.console.configure(state='disabled')

    def flush(self):
        pass

    def choose(self):
        filename = filedialog.askopenfilename(
            initialdir=str(DEFAULT_IMAGE.parent),
            initialfile=DEFAULT_IMAGE.name,
            filetypes=[('Filesystem image', '*.img'), ('All files', '*.*')],
        )
        if filename:
            self.restart(filename)

    def reload(self):
        if self.source:
            self.restart(str(self.source))

    def restart(self, source):
        command = [sys.executable, str(Path(__file__).resolve()), source]
        if not self.online.get():
            command.append('--offline')
        subprocess.Popen(command, cwd=str(Path(__file__).resolve().parent))
        self.close()

    def boot(self):
        if not self.source:
            return
        try:
            FatImage(self.source).extract(self.root)
            if not (self.root / 'main.py').is_file():
                raise ValueError('Image contains no main.py')
            self.context = runtime(self.root, self.network)
            self.context.__enter__()
            self.status.set('Running: ' + self.source.name + ' • Wi-Fi is simulated')
            with contextlib.redirect_stdout(self), contextlib.redirect_stderr(self):
                if (self.root / 'boot.py').exists():
                    runpy.run_path(str(self.root / 'boot.py'), run_name='__boot__')
                self.scope = runpy.run_path(str(self.root / 'main.py'), run_name='__main__')
            self.refresh()
        except Exception:
            self.status.set('Application failed — see console below')
            self.write(traceback.format_exc())

    def refresh(self):
        self.hits = lv.render()

    def invoke(self, action):
        try:
            with contextlib.redirect_stdout(self), contextlib.redirect_stderr(self):
                action()
            self.refresh()
        except Exception:
            self.status.set('Application callback failed — see console below')
            self.write(traceback.format_exc())

    def move(self, dx, dy):
        for view in lv.tileviews():
            self.invoke(lambda v=view: v.move(dx, dy))

    def down(self, event):
        self.canvas.focus_set()
        self.press = (event.x, event.y)
        self.drag_mode = None
        self.drag_tile = self.tile_at(event.x, event.y)
        self.drag_scroll_y = self.drag_tile.get_scroll_y() if self.drag_tile else 0

    def tile_at(self, x, y):
        for x1, y1, x2, y2, node in reversed(self.hits):
            if hasattr(node, 'coord') and x1 <= x < x2 and y1 <= y < y2:
                return node
        return None

    def drag(self, event):
        dx, dy = event.x - self.press[0], event.y - self.press[1]
        if self.drag_mode is None and max(abs(dx), abs(dy)) >= 8:
            if abs(dy) > abs(dx) and self.drag_tile and self.drag_tile.can_scroll_y(-dy):
                self.drag_mode = 'scroll'
            else:
                self.drag_mode = 'swipe'
        if self.drag_mode == 'scroll':
            self.invoke(lambda: self.drag_tile.scroll_to_y(self.drag_scroll_y - dy))

    def wheel(self, event, delta=None):
        if delta is None:
            raw = getattr(event, 'delta', 0)
            if not raw:
                return
            delta = -raw / 120 * 60 if abs(raw) >= 120 else -raw * 3
        tile = self.tile_at(event.x, event.y)
        if tile and tile.can_scroll_y(delta):
            self.invoke(lambda: tile.scroll_to_y(tile.get_scroll_y() + delta))
        return 'break'

    def up(self, event):
        self.drag(event)
        dx, dy = event.x - self.press[0], event.y - self.press[1]
        if self.drag_mode == 'scroll':
            self.drag_mode = None
            return
        if max(abs(dx), abs(dy)) >= 50:
            if abs(dx) >= abs(dy):
                self.move(-1 if dx > 0 else 1, 0)
            else:
                self.move(0, -1 if dy > 0 else 1)
        elif self.drag_mode is None:
            for x1, y1, x2, y2, node in reversed(self.hits):
                if (x1 <= event.x < x2 and y1 <= event.y < y2
                        and x1 <= self.press[0] < x2 and y1 <= self.press[1] < y2
                        and (node.events or node.has_flag(lv.obj.FLAG.CLICKABLE))):
                    self.invoke(node.click)
                    break
        self.drag_mode = None

    def close(self):
        if self.context:
            self.context.__exit__(None, None, None)
            self.context = None
        self.window.destroy()
        self.temp.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?', help='FAT12/16 VFS image')
    parser.add_argument('--offline', action='store_true', help='Simulate Wi-Fi connection failure')
    parser.add_argument('--list', action='store_true', help='List image files without executing them')
    args = parser.parse_args()
    if args.list:
        if not args.image:
            parser.error('--list requires an image')
        for name, content in FatImage(args.image).files().items():
            print('%8d  %s' % (len(content), name))
        return
    app = Simulator(args.image, args.offline)
    app.window.after(50, app.boot)
    app.window.mainloop()


if __name__ == '__main__':
    main()
