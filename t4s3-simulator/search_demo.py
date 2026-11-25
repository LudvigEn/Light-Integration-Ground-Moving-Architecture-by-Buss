"""Try all three searchable stop selectors without changing project/.

Run: python t4s3-simulator/search_demo.py
"""
import json
from pathlib import Path

import lvgl_sim as lv
from search_dropdown import add_dropdown_search
from simulator import Simulator


def build_demo():
    """Create the same search adapter for Stop, From and To."""
    root = Path(__file__).resolve().parents[1]
    font_path = root / 'project' / 'fonts' / 'transit_16.bin'
    font = lv.binfont_create_from_buffer(font_path.read_bytes())
    font.fallback = lv.font_montserrat_16
    screen = lv.screen_active()
    screen.set_style_text_font(font, 0)
    screen.set_style_bg_color(lv.color_hex(0xF3F5F7), 0)
    names = sorted(json.loads((root / 'project' / 'STOPS.json').read_text(encoding='utf-8'))['ALL'])
    title = lv.label(screen)
    title.set_pos(30, 20)
    title.set_text('Search stops with the touch keyboard')
    selections = {}
    for row, name in enumerate(('Stop', 'From', 'To')):
        label = lv.label(screen)
        label.set_pos(30, 92 + row * 90)
        label.set_text(name)
        control = lv.dropdown(screen)
        control.set_pos(110, 80 + row * 90)
        control.set_width(410)
        control.set_style_text_font(font, 0)
        control.get_list().set_style_text_font(font, 0)
        control.set_options('\n'.join(names))
        if 'Campus Gräsvik' in names:
            control.set_selected(names.index('Campus Gräsvik'))
        selections[name] = control
        add_dropdown_search(screen, control, font, 535, 80 + row * 90)
    hint = lv.label(screen)
    hint.set_pos(30, 370)
    hint.set_width(540)
    hint.set_text('Tap Find. Type with the touch keyboard or your computer.\n'
                  'Choose a result and confirm with the tick. Cross cancels.')
    return selections


def main():
    app = Simulator(None)
    app.source = None
    app.window.title('LilyGO T4-S3 - Searchable dropdown demo')
    build_demo()
    app.status.set('Search demo - project files are read only')
    app.refresh()
    app.window.mainloop()


if __name__ == '__main__':
    main()
