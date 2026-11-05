# T4-S3 desktop simulator

Run `Launch.cmd`, or run `python simulator.py` using a Python environment with
Tkinter, Pillow (for image recoloring), and the dependencies imported by your
application (currently `requests`).

Install dependencies with `python -m pip install -r requirements.txt` from this
directory, using the Python runtime that launches the simulator. `Launch.cmd`
prefers the bundled Codex runtime when present:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r requirements.txt
```

The simulator automatically opens `../device-build/t4s3-vfs.img` when it
exists, falling back to `t4s3-vfs-deploy.img` if only that file is available.
The Open image dialog defaults to the full image's directory and filename.
An image passed on the command line overrides the startup default. Paths for
the default image are resolved relative to the simulator, not the terminal's
working directory.

After changing files under `project/`, rebuild with PlatformIO's **Build Python
application** task and use **Reset / Reload**. If you explicitly open a truncated
`t4s3-vfs-deploy.img`, the simulator automatically uses the sibling
`t4s3-vfs.img` when its bytes match the deployment image's prefix. A console
message explains the substitution. Missing or mismatched full images still
produce an error; missing file contents are never filled in or ignored.
Full and trimmed images in the same directory share saved simulator settings.

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

## PNG images and the license screen

The simulator supports `lv.image(parent)`, `set_src`, `get_src`, `center`, and
`align(lv.ALIGN.CENTER, x, y)` for PNG files. It supplies the MicroPython
`fs_driver` module and `lv.fs_drv_t` registration interface:

```python
import fs_driver

self.image_fs = lv.fs_drv_t()
fs_driver.fs_register(self.image_fs, "S")
self.qr_image = lv.image(self.qr_scr)
self.qr_image.set_src("S:/assets/QR_Black_On_White.png")
self.qr_image.center()

# In apply_colors(), after choosing the theme's foreground color:
self.qr_image.set_style_image_recolor(foreground_color, 0)
self.qr_image.set_style_image_recolor_opa(lv.OPA.COVER, 0)
```

`S:/assets/...` and `S:assets/...` resolve inside the extracted filesystem image.
Place the PNGs in `project/assets/` and rebuild the application image. Files in
the repository's top-level `assets/` directory are not packaged automatically.
Missing files and unregistered drive letters produce explicit console errors.
Drive registrations are isolated between simulated runs.

The transparent `QR_Black_On_White.png` can serve both themes: recolor its modules
black in light mode and white in dark mode. Transparent pixels stay transparent,
revealing the tile's background. Recoloring an opaque image also tints its
background, so use the transparent asset for this approach. The default recolor
opacity is `lv.OPA.TRANSP` (original colors); `lv.OPA.COVER` fully replaces colors,
and values from 0 to 255 blend toward the selected color without changing alpha.
Only the default selector (`0` / `lv.PART.MAIN`) is supported.

Reusing the same source and recolor styles keeps the rendered Tk image; changing
the source or styles updates it. `set_src(None)` clears the image while retaining
its styles for the next source. Switching between separate PNGs still works.

PNG images display at their native dimensions, with no implicit resizing.
Resize the source PNGs before packaging if they do not fit the screen.
Only file-backed images are supported; LVGL image descriptors, transformations,
and custom decoder/filesystem callbacks are not emulated.

A license tile at `(1, 1)` with `lv.DIR.TOP` can be reached from Settings at
`(1, 0)` when Settings allows `lv.DIR.BOTTOM`. Swipe upward to enter the lower
tile and downward to return, or use the Down/Up arrow keys. Use the LVGL names
`TOP` and `BOTTOM`; `UP` and `DOWN` are not direction constants.

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

Image checks use real Tk PNG decoding and rendering, including the QR assets,
theme switching, vertical navigation, missing-file errors, and filesystem
registration cleanup. Run `python -m unittest test_simulator.ImageTests -v`
to check these without needing a built application image. If image integration
checks still report old application errors such as `lv.DIR.DOWN`, rebuild the
application image: the simulator deliberately executes the image's code rather
than silently substituting files from `project/`.

Run `python -m unittest test_simulator.WidgetTests -v` for widget and gesture
checks that do not need a window or an application image.
