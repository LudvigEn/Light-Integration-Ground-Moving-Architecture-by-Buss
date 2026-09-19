# T4-S3 desktop simulator

Run `Launch.cmd`, or run `python simulator.py` using a Python environment with
Tkinter and the dependencies imported by your application (currently `requests`).

The simulator automatically opens `../device-build/t4s3-vfs-deploy.img` when it
exists. The Open image dialog defaults to that directory and filename too.
An image passed on the command line overrides the startup default. Paths for
the default image are resolved relative to the simulator, not the terminal's
working directory.

After changing files under `project/`, rebuild with PlatformIO's **Build Python
application** task and use **Reset / Reload**. If a deployment image becomes too
small to contain all allocated files, open the full `t4s3-vfs.img` instead.

## Controls

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

Tile scrolling works automatically when its direct children extend below its
height. A hidden scrollbar does not disable scrolling. To disable user scrolling,
use `tile.remove_flag(lv.obj.FLAG.SCROLLABLE)`; use `add_flag` to enable it again.
`set_scroll_dir(lv.DIR.VER)` restricts gestures to vertical scrolling.
`get_scroll_y()` reads the offset and `scroll_to_y(y, lv.ANIM.OFF)` sets it.

This is a small compatibility layer, not a complete LVGL implementation.
Scrolling currently applies to whole tiles, including their headings; nested
scrollable containers, scrollbars, inertia, and scroll animations are not
implemented. Switch rendering uses a simple fixed palette.

## Verification

Run `python test_simulator.py` to check widgets, gestures, image extraction,
and the current application's startup and dark-mode switch. The integration
check uses a hidden Tk window and the default application image. Pass another
image path as an argument to override it. The application should use local
test data for these checks.

Run `python -m unittest test_simulator.WidgetTests -v` for widget and gesture
checks that do not need a window or an application image.
