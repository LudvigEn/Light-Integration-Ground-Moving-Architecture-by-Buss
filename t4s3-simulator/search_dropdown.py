"""Portable LVGL example: a search popup for an existing stop dropdown.

This module is a simulator example, not automatically injected into the app.
Its add_dropdown_search function can also be copied into a MicroPython app.
"""
try:
    import lvgl as lv
except ImportError:
    import lvgl_sim as lv


def add_dropdown_search(parent, dropdown, font, x, y):
    """Place a search button beside a dropdown on a 600 by 450 display."""
    trigger = lv.button(parent)
    trigger.set_pos(x, y)
    trigger.set_size(40, 40)
    trigger.set_style_text_font(font, 0)
    icon = lv.label(trigger)
    icon.set_text("Find")
    icon.center()

    def open_search(_event):
        dropdown.close()
        # Read fresh options each time, including transport-type changes.
        names = dropdown.get_options().splitlines()
        index = dropdown.get_selected()
        selected = names[index] if 0 <= index < len(names) else None

        panel = lv.obj(lv.screen_active())
        panel.set_pos(0, 0)
        panel.set_size(600, 450)
        panel.set_style_pad_all(0, 0)
        panel.remove_flag(lv.obj.FLAG.SCROLLABLE)
        panel.add_flag(lv.obj.FLAG.CLICKABLE)
        panel.set_style_bg_color(lv.color_hex(0xF3F5F7), 0)
        panel.set_style_bg_opa(lv.OPA.COVER, 0)
        panel.set_style_text_color(lv.color_hex(0x101820), 0)
        panel.set_style_text_font(font, 0)

        field = lv.textarea(panel)
        field.set_one_line(True)
        field.set_pos(20, 20)
        field.set_size(560, 42)
        field.set_max_length(60)
        field.set_placeholder_text("Search stop...")
        field.set_text("")

        results = lv.dropdown(panel)
        results.set_pos(20, 80)
        results.set_width(560)
        results.set_style_text_font(font, 0)
        results.get_list().set_style_text_font(font, 0)
        results.get_list().set_style_max_height(80, 0)

        status = lv.label(panel)
        status.set_pos(20, 130)
        status.set_width(560)

        keys = lv.keyboard(panel)
        keys.set_size(600, 240)
        keys.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keys.set_style_text_font(font, lv.PART.ITEMS)
        key_map = list("qwertyuiopå") + ["\n"] + list("asdfghjklöä") + ["\n"]
        key_map += list("zxcvbnm-") + [lv.SYMBOL.BACKSPACE, "\n"]
        key_map += [lv.SYMBOL.CLOSE, lv.SYMBOL.LEFT, " ", lv.SYMBOL.RIGHT, lv.SYMBOL.OK, ""]
        controls = [4 if key == " " else 1 for key in key_map if key not in ("", "\n")]
        keys.set_map(lv.keyboard.MODE.USER_1, key_map, controls)
        keys.set_mode(lv.keyboard.MODE.USER_1)
        keys.set_textarea(field)
        matches = []

        def normalize(text):
            # Explicit replacements also work with MicroPython's ASCII lower().
            return text.replace("Å", "å").replace("Ä", "ä").replace("Ö", "ö").lower()

        def filter_names(_event=None):
            nonlocal matches
            query = normalize(field.get_text().strip())
            matches = [name for name in names if query in normalize(name)]
            results.set_options("\n".join(matches))
            if matches:
                results.remove_state(lv.STATE.DISABLED)
                results.set_selected(matches.index(selected) if selected in matches else 0)
                status.set_text("%d matches. Open the list, choose a stop, then press the tick." % len(matches))
            else:
                results.add_state(lv.STATE.DISABLED)
                status.set_text("No matching stops. Change the search, or close to cancel.")

        def finish(event):
            code = event.get_code()
            if code == lv.EVENT.READY:
                if not matches:
                    return
                chosen = matches[results.get_selected()]
                dropdown.set_selected(names.index(chosen))
            elif code != lv.EVENT.CANCEL:
                return
            keys.set_textarea(None)
            panel.delete()
            if code == lv.EVENT.READY:
                # Programmatic selection does not notify existing callbacks.
                dropdown.send_event(lv.EVENT.VALUE_CHANGED, None)

        field.add_event_cb(filter_names, lv.EVENT.VALUE_CHANGED, None)
        # LVGL keeps pointers to custom maps; retain their buffers as user data.
        field.add_event_cb(finish, lv.EVENT.READY, (key_map, controls))
        field.add_event_cb(finish, lv.EVENT.CANCEL, (key_map, controls))
        filter_names()

    trigger.add_event_cb(open_search, lv.EVENT.CLICKED, None)
    return trigger
