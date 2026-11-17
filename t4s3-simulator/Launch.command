#!/bin/sh
# Works from Finder or Terminal, including checkout paths containing spaces.
SIM_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
SIM_PYTHON=${SIM_PYTHON:-"$SIM_DIR/.venv/bin/python"}
if [ ! -x "$SIM_PYTHON" ]; then
    SIM_PYTHON=python3
fi
"$SIM_PYTHON" -c 'import tkinter; import PIL' || {
    printf '\nPython with Tkinter and Pillow is required. See %s/README.md\n' "$SIM_DIR" >&2
    exit 1
}
# Do not change directory: relative image arguments belong to the caller.
exec "$SIM_PYTHON" "$SIM_DIR/simulator.py" "$@"
