# LilyGO T4-S3 desktop simulator

Run the device's Python application from a FAT filesystem image on Windows,
macOS, or Linux. The simulator uses Python, Tkinter and Pillow; no board is
required. It implements the LVGL features used by this project, not all of LVGL.

## macOS setup

Use Python 3.10 or newer with Tkinter. Check your installation with
`python3 -m tkinter`: a small test window should open. If Tkinter is missing,
install a Python distribution that includes Tk support before continuing.

From the repository root, create the simulator environment once:

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

In VS Code, run **PlatformIO > Project Tasks > t4s3-micropython > Custom >
Build Python application** to generate `device-build/t4s3-vfs.img` without
flashing a board. The simulator automatically opens this image when present.
Otherwise, use **Open image…**, or pass an image explicitly:

```sh
sh t4s3-simulator/Launch.command "/path/to/t4s3-vfs.img" --local-data
```

`--local-data` uses the image's bundled departure test data instead of the live
API. `--offline` simulates disconnected Wi-Fi. Rebuild the image after changing
the application, then click **Reset / Reload**. Saved device settings persist
in `.state/`; use `--state-dir PATH` for a separate simulated device.

Drag sideways to switch tiles, drag vertically or scroll to move a list, and
click to touch. Arrow keys also switch tiles.

## Windows

Install the dependencies with `py -3 -m pip install -r
t4s3-simulator/requirements.txt`, then run `t4s3-simulator/Launch.cmd`, or:

```powershell
py -3 t4s3-simulator/simulator.py --local-data
```

## Verification

With a built application image and a desktop session available:

```sh
t4s3-simulator/.venv/bin/python -m unittest discover -s t4s3-simulator -p 'test_*.py'
```
