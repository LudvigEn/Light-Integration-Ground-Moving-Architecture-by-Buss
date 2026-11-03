# T4-S3 desktop simulator

Run `Launch.cmd`, or run `python simulator.py` using a Python environment with
Tkinter and the dependencies imported by your application (currently `requests`).

Install dependencies with `python -m pip install -r requirements.txt` from this
directory, using the Python runtime that launches the simulator. `Launch.cmd`
prefers the bundled Codex runtime when present:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r requirements.txt
```

The simulator automatically opens `../device-build/t4s3-vfs-deploy.img` when it
exists. The Open image dialog defaults to that directory and filename too.
An image passed on the command line overrides the startup default. Paths for
the default image are resolved relative to the simulator, not the terminal's
working directory.

After changing files under `project/`, rebuild with PlatformIO's **Build Python
application** task and use **Reset / Reload**. If a deployment image becomes too
small to contain all allocated files, open the full `t4s3-vfs.img` instead.

## Data and settings

The current application creates its departure rows when you enter the departures
tile. Live API calls are the default and use the credentials in the image. Check
**Local test data**, or launch with `python simulator.py --local-data`, to serve
the bundled Campus Gräsvik snapshot instead. This snapshot is used regardless of
the selected stop and needs no working API key. It still runs the application's
real parsing and rendering code. You can change this option while running.

**Simulated Wi-Fi** now also controls HTTP connectivity: unchecking it causes
requests to fail, so you can exercise the application's error message. Recheck
it and re-enter the departures tile to retry. Starting with `--offline` exercises
the application's Wi-Fi startup timeout too.

The SAVE button writes `settings.txt` in the extracted simulated filesystem.
After callbacks, on reset, and on close, the simulator saves a copy under
`.state/<image-path-hash>/settings.txt`. It restores this copy on the next launch
of the same image path, including after **Reset / Reload**. This directory is
ignored by Git. Delete that image's saved copy while the simulator is closed to
restore the defaults from the image. `--state-dir PATH` selects another storage
directory. The original `.img` is never modified, and simulated settings do not
alter the physical device's settings.

Application modules and MicroPython timing functions are isolated for each run.
`time.ticks_ms`, `ticks_us`, `ticks_diff`, `ticks_add`, `sleep_ms`, and `sleep_us`
are available while the application runs, so the project's timing logs work.
These are desktop execution timings, not ESP32 performance predictions.

## Controls

- Dropdowns support `lv.dropdown(parent)`, newline-separated `set_options`,
  `set_selected`, `get_selected`, `get_options`, and `get_option_count`.
  Click to open and pick an option; a changed selection emits
  `lv.EVENT.VALUE_CHANGED`. Click outside to dismiss. Programmatic selection
  does not emit an event. Popup lists currently do not scroll, so keep options
  short enough to fit the display.
- Dropdown popups follow the control's background and text colors by default.
  Use `dropdown.get_list()` with `set_style_bg_color` or `set_style_text_color`
  to override the popup colors: `lv.PART.MAIN` styles ordinary rows and
  `lv.PART.SELECTED` (optionally combined with `lv.STATE.CHECKED`) styles the
  selected row. The default selected row uses white text on blue.
  Button labels inherit their parent's text color unless explicitly styled.
- Widgets support `set_style_border_width(pixels, 0)` and
  `set_style_border_color(color, 0)` for rectangular borders inside their bounds.
  A width of zero removes the border.
- Cursor x/y coordinates appear below the display, measured in pixels from its
  top-left corner (0, 0), and update while moving or dragging within the window.
- Click a switch to toggle it. Switches support `lv.STATE.CHECKED`,
  `lv.STATE.DISABLED`, `add_state`, `remove_state`, and `has_state`.
- User toggles emit `lv.EVENT.VALUE_CHANGED`, followed by `lv.EVENT.CLICKED`.
  Setting the checked state in code does not invoke the change callback.
- Drag vertically or use the mouse wheel over a tile to scroll overflowing
  content. Dragging does not also click a control. Scrolling stops at the
  content's top and bottom.
- Swipe horizontally or use the arrow keys to change tiles. Vertical swipes
  navigate between vertical tiles when the current tile has no vertical
  overflow. Arrow keys always navigate tiles.
- Tile changes emit `lv.EVENT.VALUE_CHANGED`; `tileview.get_tile_active()`
  identifies the destination. `container.clean()` removes its children so
  an application can rebuild a tile's contents each time it is entered.
- Events support `get_target_obj()` and `get_current_target_obj()`, as used by
  the current device application, plus `get_code`, `get_user_data`, and
  `get_param`. `send_event(code, param=None)` accepts an optional event parameter.
- The current departure table's explicit zero-padding and zero-theme-border
  calls are supported. Its nested boxes keep their scroll flags; only the outer
  tile scrolls in the simulator.
- Font size and inheritance follow `set_style_text_font`. Built-in Montserrat
  previews substitute a square for unsupported characters, including ÅÄÖåäö,
  to expose the device font limitation. Text values and saved files retain the
  original Unicode characters. A font with those glyphs is still needed on the
  device.

Tile scrolling works automatically when its direct children extend below its
height. A hidden scrollbar does not disable scrolling. To disable user scrolling,
use `tile.remove_flag(lv.obj.FLAG.SCROLLABLE)`; use `add_flag` to enable it again.
`set_scroll_dir(lv.DIR.VER)` restricts gestures to vertical scrolling.
`get_scroll_y()` reads the offset and `scroll_to_y(y, lv.ANIM.OFF)` sets it.

This is a small compatibility layer, not a complete LVGL implementation.
Scrolling currently applies to whole tiles, including their headings; nested
scrollable containers, scrollbars, inertia, and scroll animations are not
implemented. Switch rendering uses a simple fixed palette. The device's default
theme padding and borders are not reproduced; the explicit styling in the
current departure rows is supported. Tk uses Arial for glyph shapes, so this is
not a pixel-perfect Montserrat preview. The legacy `get_target()` also returns
an object here; use `get_target_obj()` for device-compatible object comparisons.
The simulator runs desktop Python: it does not reproduce MicroPython dictionary
iteration order. Keep the project's explicit sorted dropdown options.

## Verification

Run `python test_simulator.py` to check widgets, gestures, image extraction,
and the current application's startup, dropdowns, dark-mode switch, departure
refresh, timing logs, SAVE button, and settings persistence. The integration
check uses a hidden Tk window and the default application image. Pass another
image path as an argument to override it. Integration checks automatically use
local test data and temporary settings storage; they do not call the live API
or modify your saved simulator settings.

Run `python -m unittest test_simulator.WidgetTests -v` for widget and gesture
checks that do not need a window or an application image.
