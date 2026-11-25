# LilyGO T4-S3 desktop simulator

Run the device's Python application from a FAT filesystem image on Windows,
macOS, or Linux. The simulator uses Python, Tkinter and Pillow; no board is
required. It implements the LVGL features used by this project, not all of LVGL.

## Sharing with classmates

This is a portable Python application for Windows, macOS and Linux, not a
standalone executable. Classmates need Python 3.10 or newer with Tkinter, the
dependencies below, and their own built application image. They do not need
Codex or a connected board to run it.

From a repository checkout, create a clean shareable ZIP with:

```sh
python t4s3-simulator/package_simulator.py
```

Send `t4s3-simulator/dist/t4s3-simulator.zip`. It includes the simulator, fonts,
licenses, launchers and sample departure data. It excludes virtual environments,
saved settings, caches and device images. Application images contain the
project's `secrets.py`, so each classmate should build their own image.
Extract the ZIP before launching; keep its folders together.

## macOS setup

Use Python 3.10 or newer with Tkinter. Check your installation with
`python3 -m tkinter`: a small test window should open. If Tkinter is missing,
install a Python distribution that includes Tk support before continuing.

From the parent of `t4s3-simulator` (the repository root or ZIP extraction
directory), create the simulator environment once:

```sh
python3 -m venv t4s3-simulator/.venv
t4s3-simulator/.venv/bin/python -m pip install -r t4s3-simulator/requirements.txt
chmod +x t4s3-simulator/Launch.command
```

Then double-click `Launch.command` in Finder, or run from Terminal:

```sh
sh t4s3-simulator/Launch.command --local-data
```

The launcher uses `t4s3-simulator/.venv/bin/python` when present, otherwise
`python3` on PATH. Set `SIM_PYTHON` to an executable Python path to override it.
The same Terminal commands also work on Linux with Tkinter installed.

## Application image

From a repository checkout, use **Run Python File** on `project/main.py` in
VS Code to build the application image with PlatformIO and then launch the
simulator. PlatformIO must be installed, along with the simulator dependencies
described in this README. If the build fails, the simulator does not start.

In VS Code, run **PlatformIO > Project Tasks > t4s3-micropython > Custom >
Build Python application** to generate `device-build/t4s3-vfs.img` without
flashing a board. The simulator automatically opens this image when present.
For a standalone copy, place the full `t4s3-vfs.img` beside `simulator.py` to
open it automatically. Otherwise, use **Open image…**, or pass an image explicitly:

```sh
sh t4s3-simulator/Launch.command "/path/to/t4s3-vfs.img" --local-data
```

`--local-data` uses bundled sample departures instead of the live API, without
requiring an API key. A `test_data/stop_740032188_formatted.json` in the image
overrides the simulator's sample. `--offline` simulates disconnected Wi-Fi.
Rebuild the image after changing
the application, then click **Reset / Reload**. Saved device settings persist
in `.state/`; use `--state-dir PATH` for a separate simulated device.

Drag sideways to switch tiles, drag vertically or scroll to move a list, and
click to touch. Open dropdown lists stay within the display: use the mouse wheel
or drag vertically inside the popup to reach more options. A scrollbar shows
your position, and reopening the list brings the selected option into view.
Arrow keys also switch tiles.

`screen.invalidate()` queues a redraw, including visible child widgets. The
next simulator refresh pass draws it even when no application timers are due.
`lv.refr_now(None)` redraws immediately and flushes the Tk canvas without
running application events or timers. The simulator repaints the full canvas
rather than tracking individual dirty rectangles. These calls do not reload
settings, fetch data, rebuild widgets, or copy Python attributes into controls.

Tabs in bitmap-font text use LVGL's two-space glyph advance, including when
the space comes from a fallback font. They do not use editor-style tab stops.

## Searchable stop selectors

The simulator supports `lv.textarea`, `lv.keyboard`, custom keyboard maps,
READY/CANCEL events, and bounded dropdown lists for touch search popups. Tap a
text field to edit it using the on-screen keyboard or your computer keyboard.
Left/Right move the text cursor while editing; Enter confirms and Escape cancels.

`align()` supports `CENTER`, `TOP_LEFT`, `TOP_MID` and `BOTTOM_MID`, with anchors
that follow widget and parent resizing. Keyboards start bottom-middle aligned,
as on the device; use `keys.align(lv.ALIGN.BOTTOM_MID, 0, 0)` to keep the keyboard
inside the panel without a downward offset.

Try the three-selector example from a repository checkout, without modifying
or rebuilding the device application:

```powershell
python t4s3-simulator/search_demo.py
```

Use the same Python environment as the simulator (Python 3.10+, Tkinter and
Pillow). On macOS/Linux use `python3`, or your simulator virtual environment.
Tap **Find** beside Stop, From or To. Type a name (the touch layout includes
å, ä, ö), open the filtered list, choose a result, and confirm with the tick.
The cross cancels; an empty result set cannot be confirmed. Long result lists
scroll within their popup above the keyboard.

The reusable LVGL example is in `search_dropdown.py`. It uses the current
options of each dropdown when opened, preserves the full list, and sends
VALUE_CHANGED only after confirmation so existing selection callbacks work.
This is an example for you to apply to the device app; it is not automatically
injected into application images. The demo reads the repository's stop list
and custom font and does not make API requests.

The input implementation covers the one-line search workflow, basic cursor
editing and custom key widths. Password modes, text selection, custom
button-matrix control flags and keyboard key popovers are not implemented.

## Testing WIFI_LIST

Wi-Fi is simulated; it does not change the computer's real Wi-Fi connection.
By default every configured SSID is accepted, so the first entry succeeds.
To test fallback, enter a network name from a later `WIFI_LIST` entry in
**Available SSID**, then click **Reset / Reload**. Only that name will be
available, so the application's existing loop can try earlier entries and
advance to the matching one. The simulator accepts any password for an
available SSID; use the physical board to test real authentication.

You can also set this at launch:

```sh
python t4s3-simulator/simulator.py --wifi-ssid "Phone hotspot" --local-data
```

Clear the field and reload to accept any SSID again. **Simulated Wi-Fi**
controls whether the simulated network is online. Live API requests still use
the computer's existing internet connection.

## Windows

Install Python 3.10 or newer with Tkinter, then run these commands from the
parent of `t4s3-simulator` once:

```powershell
py -3 -m venv t4s3-simulator/.venv
t4s3-simulator/.venv/Scripts/python.exe -m pip install -r t4s3-simulator/requirements.txt
```

Double-click `t4s3-simulator/Launch.cmd`, or run it with `--local-data` in a
terminal. The launcher uses `SIM_PYTHON` when set, then the local virtual
environment, an available Codex Python runtime, or system Python. A Codex
installation is optional. Launchers preserve the caller's directory for
relative image paths.

## Verification

From a repository checkout, with a built application image and a desktop
session available:

```sh
t4s3-simulator/.venv/bin/python -m unittest discover -s t4s3-simulator -p 'test_*.py'
```
