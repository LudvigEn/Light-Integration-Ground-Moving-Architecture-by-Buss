# Simulator built-in font assets

`sim_montserrat_12.bin` through `sim_montserrat_48.bin` contain printable
ASCII, degree, bullet, and the visible built-in symbols defined by LVGL.
These are simulator resources, not files that need to be packaged on the device.

Generated using `lv_font_conv` 1.5.3, uncompressed 4-bpp binary output, from:

- Montserrat Medium 7.200:
  https://github.com/lvgl/lvgl/blob/v9.2.2/scripts/built_in_font/Montserrat-Medium.ttf
- LVGL's combined Font Awesome Solid + Brands + Regular source:
  https://github.com/lvgl/lvgl/blob/v9.2.2/scripts/built_in_font/FontAwesome5-Solid%2BBrands%2BRegular.woff
- Symbol names and UTF-8 strings from `src/font/lv_symbol_def.h` in LVGL
  v8.0.2 and v9.2.2. The union is recorded in `symbols.json`.

The symbol ranges are all code points in `symbols.json` other than
`BULLET` (included with the text font) and `DUMMY` (not a visible glyph).
For text use `--range 0x20-0x7E,0xB0,0x2022`, then merge the symbol ranges
from the Font Awesome WOFF with `--font`, `--size SIZE`, `--bpp 4`,
`--no-compress`, and `--format bin`.

The font assets are licensed under SIL OFL 1.1; retain the accompanying
license notices. Embedded source attribution: Copyright 2011 The Montserrat
Project Authors; Copyright (c) Font Awesome. The derived font name is
Simulator Montserrat; the name of the icon source identifies attribution only.

Normal built-in text remains an Arial approximation. The bitmap assets are
used for built-in symbols and fallback resolution. User-loaded binary fonts
are always rendered directly from their glyph data.
