# LilyGO T4-S3 Python application simulator

A working prototype for the supplied MicroPython course image. Runs its Python
application in CPython and renders a small, explicit LVGL subset in a 600 × 450
Tk window. No third-party packages are required; install Python 3.10+ with Tkinter.

## Run

```powershell
python simulator.py "E:\Plugg\Software Development\Light Integration Ground Moving Architecture by Buss\device-build\t4s3-vfs-deploy.img"
```

On this computer, double-click `Launch.cmd` (it uses the bundled Python when
available, otherwise the Windows Python launcher), then select **Open image**.
Or run `python simulator.py` and select **Open image**. Drag left/right to swipe,
click to touch, or use the arrow keys. The supplied application shows two tiles;
clicking the second toggles its colors. **Reset / Reload** starts a fresh process
and rereads the image. Rebuild the image after changing your project code.

The Wi-Fi checkbox controls a simulated connection; it does not connect to an
access point. Start with `--offline` to test the application's connection timeout
(the current application blocks startup for up to 15 seconds in this mode).

```powershell
python simulator.py "path\to\image.img" --list
python test_simulator.py "path\to\t4s3-vfs-deploy.img"
```

## What works

- Direct reading of FAT12/16 filesystem images, long filenames and subdirectories.
- Trimmed deploy images when all allocated application data is present. If missing
  data is detected, use the full `t4s3-vfs.img` instead.
- Execution of image `boot.py`, then `main.py`; normal Python imports from the image.
- Board startup replacement, LVGL objects, labels, buttons, tileviews, simple
  positioning, solid backgrounds, text styles and click callbacks.
- Mouse swipes and clicks; Wi-Fi station state; MicroPython tick/sleep helpers.
- Application console and tracebacks. Common `/path` calls through `open` and
  `os.listdir` are redirected into a temporary extracted filesystem.
- Source image stays unchanged; temporary app writes are discarded on exit.

## Scope and limitations

This is an application simulator, not an ESP32 CPU emulator or native MicroPython
runtime. It does not boot the ESP32 firmware binary. Unsupported LVGL calls raise
errors. Tk uses desktop fonts and simplified layout; output is not pixel-identical
to native LVGL. Animation, LVGL timers, flex/grid, images, arbitrary hardware
drivers, GPIO, I2C, SPI, interrupts, power behavior and memory limits are not
implemented. `start_board()` returns placeholder handles; direct handle use is
unsupported. New application APIs require extending the compatibility layer.

The current template returns after setting up callbacks, which this prototype
supports. An infinite loop, long sleep or blocking request inside application code
blocks the GUI. Event-loop/async applications need additional runtime support.
The console captures startup and input callbacks, not independent background work.

Only Wi-Fi state is mocked. Actual socket/HTTP calls are not mocked or blocked and
may use the computer's network. Only `open` and `listdir` device paths are mapped;
other filesystem APIs are not virtualized. Run only trusted application images:
the Python code executes with your normal desktop permissions, not in a security
sandbox. Do not distribute images containing your Wi-Fi credentials.

FAT short names are normalized to lowercase; long names retain their case.
Encrypted images, partitioned disk images, FAT32 and LittleFS are unsupported.

For closer fidelity, the next step is a desktop MicroPython build with the same
native LVGL version as the firmware and a desktop display/input driver. Physical
device testing remains necessary for timing, peripherals and memory behavior.
MicroPython documents language differences here:
https://docs.micropython.org/en/latest/genrst/index.html
