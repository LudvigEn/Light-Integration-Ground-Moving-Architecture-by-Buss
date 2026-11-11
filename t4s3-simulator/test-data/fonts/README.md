# Binary font test fixtures

Generated from Montserrat Medium 7.200 with `lv_font_conv` 1.5.3 at 16 px.
The source and SIL OFL 1.1 notices are retained in `../../fonts/` and the
repository's `font-sources/` directory.

Character selection: `0x20,0x41-0x5A,0xC4-0xC5,0xD6,0xE4-0xE5,0xF6`.
Each bit depth has raw output (`--no-compress`); 2/3/4/8 bpp also have RLE
with XOR filtering (default) and RLE without filtering (`--no-prefilter`).
Equivalent decoded glyphs and rendered text are compared across modes.

`sample_pairs.bin` uses space, A, and V. Its converter-produced class
kerning table was replaced with the equivalent format-0 A/V pair to test
both legal binary representations independently.
