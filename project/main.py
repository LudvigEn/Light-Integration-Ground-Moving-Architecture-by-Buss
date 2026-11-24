"""File for running main-code used in the project"""
import sys # Access system utilities, including exception reporting
if (
    __name__ == "__main__"
    and sys.implementation.name == "cpython"
    and "lvgl" not in sys.modules
):
    from pathlib import Path
    from shutil import which
    import subprocess

    project_dir = Path(__file__).resolve().parents[1]
    simulator_dir = project_dir / "t4s3-simulator"

    pio = which("pio") or which("platformio")
    if pio is None:
        pio = Path.home() / ".platformio" / "penv" / (
            "Scripts/pio.exe" if sys.platform == "win32" else "bin/pio"
        )
        if not pio.is_file():
            raise SystemExit(
                "PlatformIO was not found. Install PlatformIO IDE in VS Code "
                "or add the PlatformIO CLI to PATH."
            )

    print("Building Python application with PlatformIO...", flush=True)
    build_result = subprocess.call(
        [str(pio), "run", "--environment", "t4s3-micropython",
         "--target", "build_app_fs"],
        cwd=str(project_dir),
    )
    if build_result:
        raise SystemExit(build_result)

    command = (
        ["cmd.exe", "/d", "/c", "Launch.cmd"]
        if sys.platform == "win32"
        else ["sh", "Launch.command"]
    )

    raise SystemExit(
        subprocess.call(command, cwd=str(simulator_dir))
    )  # Builds the application and runs the simulator on RUN
import json
import time # Provide timing and delay functions

import lvgl as lv # Import the LVGL graphics library # pylint: disable=import-error
import network # Access the boards network interface # pylint: disable=import-error

from board_lvgl import start_board # Import the function that initializes the display and hardware
from debug_log import log # Import the applications logging function

from secrets import WIFI_SSID, WIFI_PASSWORD, WIFI_LIST # Load the Wi-Fi network name and password

from data import read_data, find_journey # Load the data-processing module

import fs_driver # pylint: disable=import-error

VERSION = 0.5 # Version-control

class Application:
    """Class for application"""
    def __init__(self):
        print("Starting application")
        self.display, self.touch, self.handler = start_board()
        self.image_fs = lv.fs_drv_t()
        fs_driver.fs_register(self.image_fs, "S")
        self.qr_image = None
        self.font_16 = lv.binfont_create("S:/fonts/transit_16.bin")
        self.font_16.fallback = lv.font_montserrat_16
        self.font_28 = lv.binfont_create("S:/fonts/transit_28.bin")
        self.font_28.fallback = lv.font_montserrat_28
        self.icon_font_32 = lv.binfont_create("S:/fonts/transit_icons_32.bin")
        self.dark_mode = True # Dark mode toggle, default on
        self.backgrounds = [] # List of all backgrounds, for toggling dark-mode
        self.borders = [] # List of all borders (like around boxes), for toggling dark-mode
        self.labels = [] # List of all labels, for toggling dark-mode
        self.controls = [] # List of all controls (buttons/dropdowns), for toggling dark-mode
        self.journey_from: str = "Campus Gräsvik"
        self.journey_to: str = "Landsvägsgatan"
        self.journeys: list = None
        self.default_stop = "Campus Gräsvik"
        self.default_transport_type = "BUS"
        self.refresh_started: int = -100000
        self.departure_timer = None
        self.q_time = None
        module_dir = __file__.replace("\\", "/").rpartition("/")[0] or "."
        with open(module_dir + "/STOPS.json", "r", encoding="utf-8") as file:
            self.STOPS = json.load(file)
        self.wifi_name: str = self.connect_wifi() or "Offline"
        self.create_ui() # Function to trigger creation of UI
        log("student application ready")


        """Function: runs the """

    def save_settings(self):
        """Function: Save settings to file."""
        with open("settings.txt", "w", encoding="utf-8") as file:
            to_write = f"{self.default_stop}\n{self.default_transport_type}\n{self.dark_mode}"
            file.write(to_write)
            log_written = f"Saved: \n{to_write}"
            log(log_written)

    def reset_settings(self):
        """Function to reset settings by reloading setting screen"""
        log("Reset Settings called")
        self.read_settings()
        self.destroy_screen(self.settings_screen)
        self.create_settings_screen()
        self.tileview.set_tile(self.settings_screen, False)
        self.apply_colors()

    def read_settings(self):
        """If a settings.txt file is present, read the data from it
        If there are not 3 lines of text in it; revert to defaults
        """
        self.default_stop = "Campus Gräsvik"
        self.default_transport_type = "BUS"
        self.dark_mode = True
        try:
            with open("settings.txt", "r", encoding="utf-8") as file:
                lines = file.read().splitlines()
                if len(lines) != 3:
                    log("Invalid settings file; using defaults")
                    return
        except OSError as error:
            log_file_error = f"Could not read settings; using defaults: {error}"
            log(log_file_error)
            return

        self.default_stop = lines[0]
        self.default_transport_type = lines[1]
        self.dark_mode = lines[2] == "True"

    def apply_colors(self, screen="All"):
        """Function: Applies black/white to all elements depending on if Dark Mode is enabled or not"""
        background_color = lv.color_hex(0x000000 if self.dark_mode else 0xFFFFFF) # Background color, if Dark-mode: black, else white
        foreground_color = lv.color_hex(0xFFFFFF if self.dark_mode else 0x000000) # Foreground (topmost layer) color, if Dark-mode: white, else black

        def belongs_to_screen(widget):
            if screen == "All":
                return True
            while widget is not None:
                if widget == screen:
                    return True
                widget = widget.get_parent()
            return False

        for widget in self.backgrounds: # For all backgrounds
            if belongs_to_screen(widget):
                widget.set_style_bg_opa(lv.OPA.COVER, 0) # Make the background fully opaque (ogenomskinlig)
                widget.set_style_bg_color(background_color, 0) # Change background color to background_color

        for widget in self.borders: # For all borders
            if belongs_to_screen(widget):
                widget.set_style_bg_opa(lv.OPA.COVER, 0) # Make the background fully opaque (ogenomskinlig)
                widget.set_style_bg_color(foreground_color, 0) # Change foreground color to foreground_color

        for label in self.labels: # For all labels
            if belongs_to_screen(label):
                label.set_style_text_color(foreground_color, 0) # Change foreground color to foreground_color

        for control in self.controls:
            if belongs_to_screen(control):
                control.set_style_bg_opa(lv.OPA.COVER, 0)
                control.set_style_bg_color(background_color, 0)
                control.set_style_text_color(foreground_color, 0)
                control.set_style_border_color(foreground_color, 0)

        if self.qr_image is not None and belongs_to_screen(self.qr_image):
            self.qr_image.set_style_image_recolor(foreground_color, 0)
            self.qr_image.set_style_image_recolor_opa(lv.OPA.COVER, 0)
        log(f"Colors applied to {screen}")

    def toggle_dark_side(self, _event):
        """Function: Swaps dark-mode to True/False and also runs the function to swap colors."""
        self.dark_mode = self.dark_mode_switch.has_state(lv.STATE.CHECKED) ## Dark mode = State of slider
        self.apply_colors() ## Apply colors to Backgrounds, Borders and Labels

    def create_title_screen(self):
        """Function: Startup-screen"""
        self.title_screen = self.tileview.add_tile(2, 0, lv.DIR.RIGHT | lv.DIR.LEFT) # Create a screen on our tileview

        # Create labels for title-screen
        self.title_screen_label = lv.label(self.title_screen) # Add a label to the Title screen
        self.title_screen_label_group_name = lv.label(self.title_screen) # Add a label to the Title screen
        self.title_screen_label_version = lv.label(self.title_screen) # Add a label to the Title screen

        # Heading
        self.title_screen_label.set_text("L.I.G.M.A.B") # Set label to the name of the project
        self.title_screen_label.set_style_text_font(self.font_28, 0) # Set font of the label
        self.title_screen_label.align(lv.ALIGN.CENTER, 0, -100) # Place the label on the tile

        ## Group Name
        self.title_screen_label_group_name.set_text("Group 15\nLudvig En, Isac Aubert, Gösta Palmqvist,\nMelker Ruben Saar, Bastian Gralén") # Set label to the name of the members
        self.title_screen_label_group_name.set_style_text_font(self.font_16, 0) # Set font of the label
        self.title_screen_label_group_name.center() # Place the label on the tile

        ### Version
        self.title_screen_label_version.set_text(f"Version:{VERSION}") # Set label to the version of the project
        self.title_screen_label_version.set_style_text_font(self.font_16, 0) # Set font of the label
        self.title_screen_label_version.align(lv.ALIGN.CENTER, 0, 100) # Place the label on the tile

        #### Add for potential Dark/Light mode
        self.backgrounds.append(self.title_screen) # Add to list of all backgrounds
        self.labels.append(self.title_screen_label) # Add to list of all labels
        self.labels.append(self.title_screen_label_group_name) # Add to list of all labels
        self.labels.append(self.title_screen_label_version) # Add to list of all labels
        log("title-screen created")

    def destroy_screen(self, screen):
        """Clears existing departure data to be replaced with new data."""
        def belongs_to_screen(widget):
            parent = widget.get_parent()
            while parent is not None:
                if parent == screen:
                    return True
                parent = parent.get_parent()
            return False

        for widgets in (self.backgrounds, self.borders, self.labels, self.controls):
            widgets[:] = [
                widget for widget in widgets
                if not belongs_to_screen(widget)
            ]
        screen.clean()

    def on_tile_changed(self, _event):
        """Runs whenever a tile is changed"""
        if _event.get_target_obj() != self.tileview: # Ensures that we only look at changes to tiles
            return

        current_tile = self.tileview.get_tile_active()
        previous_tile = self.previous_tile

        self.previous_tile = current_tile

        if previous_tile == self.dep_scr and current_tile != self.dep_scr:
            self.stop_departure_timer()

        if previous_tile == self.settings_screen and current_tile == self.dep_scr:
            log("Swap to Departure-screen")
            self.refresh_departures()

        if previous_tile == self.journey_selection_screen and current_tile == self.journey_screen:
            log("Swap to Journey-screen")
            self.journeys, _ = find_journey(self.journey_from, self.journey_to)
            self.refresh_journeys(self.journeys)

    def refresh_journeys(self, journeys):
        """To update Journeys"""
        self.destroy_screen(self.journey_screen)

        self.journey_screen_header_label = lv.label(self.journey_screen)
        self.journey_screen_header_label.set_style_text_font(self.font_28, 0)
        self.journey_screen_header_label.set_text(f"{self.journey_from} -> {self.journey_to}")
        self.journey_screen_header_label.set_pos(10, 0)
        self.labels.append(self.journey_screen_header_label)

        y = 40
        for journey in journeys:
            journey_label = lv.label(self.journey_screen)
            journey_label.set_width(580)
            journey_label.set_style_text_font(self.font_16, 0)
            journey_label.set_text(str(journey).replace("\t", "    "))
            journey_label.set_pos(10, y)
            journey_label.update_layout()
            y += journey_label.get_height() + 16
            self.labels.append(journey_label)
        self.apply_colors(self.journey_screen)

    def refresh_departures(self):
        """To update dep"""
        self.stop_departure_timer()
        self.q_time = None
        self.destroy_screen(self.dep_scr) # Out with the old and in with the new

        transport_types = sorted(self.STOPS)
        transport_type = transport_types[
            self.transport_type_dropdown.get_selected()
        ]

        stop_names = self.stop_dropdown.get_options().splitlines()
        index = self.stop_dropdown.get_selected()

        stop = None
        message = "Select a stop in Settings."

        if 0 <= index < len(stop_names):
            stop_name = stop_names[index]
            stop_id = self.STOPS.get(transport_type, {}).get(stop_name)

            if stop_id:
                try:
                    started = time.ticks_ms() # pylint: disable=no-member
                    stop, query_time = read_data(stop_id)
                    elapsed = time.ticks_diff(time.ticks_ms(), started) # pylint: disable=no-member
                    log(f"Fetch and parsing data: {elapsed} ms")
                    if stop is not None:
                        stop.name = stop_name
                        log_departure = f"Displaying {len(stop.departures)} departures"
                        log(log_departure)
                    else:
                        message = "No data returned for the selected stop."
                except Exception as error:
                    log_error = f"Could not load departures: {error}"
                    log(log_error)
                    message = "Could not load departures. Try again!"
        started = time.ticks_ms() # pylint: disable=no-member
        if stop is not None:
            self.create_departure_screen(stop) # pylint: disable=used-before-assignment
        else:
            error_label = lv.label(self.dep_scr)
            error_label.set_text(message)
            self.labels.append(error_label)
        self.apply_colors(self.dep_scr)
        elapsed = time.ticks_diff(time.ticks_ms(), started) # pylint: disable=no-member
        if (
            self.tileview.get_tile_active() == self.dep_scr
            and self.q_time is not None
        ):
            def update_q_time(_timer=None):
                """Update the departure countdown"""
                if self.q_time is None:
                    return

                elapsed_ms = time.ticks_diff( # pylint: disable=no-member
                    time.ticks_ms(), # pylint: disable=no-member
                    self.refresh_started,
                )
                remaining_s = (max(0, 60_000 - elapsed_ms) + 999) // 1000
                if remaining_s <= 0 and self.tileview.get_tile_active() == self.dep_scr:
                    self.refresh_departures()
                    return
                self.q_time.set_text(str(remaining_s))
            update_q_time()
            self.departure_timer = lv.timer_create(
                update_q_time,
                1000,
                None,
            )
        log(f"Rendering Departure-screen: {elapsed} ms")

    def stop_departure_timer(self):
        """Stops the timer if it's running."""
        if self.departure_timer is not None:
            self.departure_timer.delete()
            self.departure_timer = None

    def create_departure_screen(self, stop):
        """Function: Show departures on a specific stop."""

        ## Name of bus-stop
        header = lv.label(self.dep_scr) # Add a label to the Departure screen
        header.set_text(stop.name) # Name of stop as header
        header.set_width(450) # Set width of label
        header.set_pos(75, 10) # Fixed position of label
        header.set_style_text_font(self.font_28, 0) # Set font of the label
        self.labels.append(header) # Add to list of labels

        self.q_time = lv.label(self.dep_scr)
        self.q_time.set_text("60")
        self.q_time.set_pos(500, 10)
        self.q_time.set_style_text_font(self.font_16, 0)
        self.labels.append(self.q_time)

        border_width = 2 # Thickness of box edges
        rows = [("Route", "Destination", "ETA", "Delay")]
        column_widths = [90, 190, 90, 90]
        transport_icons = {
            "BUS": "\uf207",
            "BOAT": "\uf21a",
            "TRAIN": "\uf238"
        }

        # We want to filter departures on selected Transport Type
        filtered_departures = [
            departure for departure in stop.departures
            if (self.default_transport_type == "ALL" or departure.route.transport_type == self.default_transport_type)
        ]
        ## For each departure, we will have a row with 3 columns; Route, Direction and Time
        for departure in filtered_departures:
            dep_timestamp = departure.realtime or departure.scheduled # Realtime if realtime exists, else scheduled
            eta = dep_timestamp[11:19] # As it's a timestamp, we only want the HH:MM:SS part, i.e. excluding the date.
            delay = departure.delay
            if departure.canceled:
                delay_text = "Cancelled"
            elif delay is None:
                delay_text = "0"
            elif delay == 0:
                delay_text = "0s"
            else:
                minutes, seconds = divmod(abs(int(delay)), 60)
                sign = "+" if delay > 0 else "-"
                delay_text = f"{sign}{minutes}m {seconds}s"
            rows.append((
                departure.route.designation,
                departure.route.destination or departure.route.direction,
                eta,
                delay_text
            ))

        for row_index, values in enumerate(rows):
            ## Box for each row
            row = lv.obj(self.dep_scr)
            row.set_style_pad_all(0, 0)
            row.set_style_border_width(0, 0)
            row.remove_flag(lv.obj.FLAG.SCROLLABLE)
            row.set_size(450, 60)
            row.set_pos(75, 55 + row_index * 70)
            self.backgrounds.append(row)

            x = 0

            # for width, value in zip(column_widths, values):
            for column_index, (width, value) in enumerate(
                zip(column_widths, values)
            ):
                ## Box in row
                outline = lv.obj(row)
                outline.set_style_pad_all(0, 0)
                outline.set_style_border_width(0, 0)
                outline.remove_flag(lv.obj.FLAG.SCROLLABLE)
                outline.set_size(width, 60)
                outline.set_pos(x, 0)
                self.borders.append(outline)

                inner = lv.obj(outline)
                inner.set_style_pad_all(0, 0)
                inner.set_style_border_width(0, 0)
                inner.remove_flag(lv.obj.FLAG.SCROLLABLE)
                inner.set_size(
                    width - 2 * border_width,
                    60 - 2 * border_width,
                )
                inner.set_pos(border_width, border_width)
                self.backgrounds.append(inner)

                label = lv.label(inner)
                label.set_width(width - 10)
                label.set_style_text_font(self.font_16, 0)
                label.set_text(str(value) if value is not None else "")
                label.center()
                self.labels.append(label)
                if column_index == 0 and row_index > 0:
                    departure = filtered_departures[row_index - 1]
                    if departure.route.transport_type in transport_icons:
                        label.set_width(width - 46)
                        label.align(lv.ALIGN.CENTER, -18, 0)

                        icon = lv.label(inner)
                        icon.set_style_text_font(self.icon_font_32, 0)
                        icon.set_text(transport_icons[departure.route.transport_type])
                        icon.align(lv.ALIGN.CENTER, 18, 1)
                        self.labels.append(icon)

                x += width
        log("Departure-screen updated")
        self.refresh_started = time.ticks_ms()

    def create_settings_screen(self):
        """Function: Create a settings screen"""


        # SETTINGS HEADER
        settings_header = lv.label(self.settings_screen)
        settings_header.set_pos(30, 20)
        settings_header.set_text("Settings")
        self.labels.append(settings_header)

        wifi_header = lv.label(self.settings_screen)
        wifi_header.set_pos(580 - len(self.wifi_name) * 10, 20)
        wifi_text = lv.SYMBOL.WIFI + self.wifi_name
        # lv.lv_label_set_text(wifi_header, LV_SYMBOL_WIFI self.wifi.name)
        wifi_header.set_text(wifi_text)
        wifi_header.set_style_text_font(self.font_16, 0)
        self.labels.append(wifi_header)

        # DARK MODE SWITCHER
        dark_mode_label = lv.label(self.settings_screen)
        dark_mode_label.set_text("Dark side")
        dark_mode_label.set_pos(75, 200)
        self.labels.append(dark_mode_label)

        self.dark_mode_switch = lv.switch(self.settings_screen)
        self.dark_mode_switch.set_pos(250, 200)
        if self.dark_mode:
            self.dark_mode_switch.add_state(lv.STATE.CHECKED)

        self.dark_mode_switch.add_event_cb(
            self.toggle_dark_side,
            lv.EVENT.VALUE_CHANGED,
            None
        )

        # TRANSPORT TYPE
        transport_type = lv.label(self.settings_screen)
        transport_type.set_text("Transport type:")
        transport_type.set_pos(75, 80)
        self.labels.append(transport_type)

        transport_type_dropdown = lv.dropdown(self.settings_screen)
        transport_type_dropdown.set_pos(200, 80)
        transport_type_dropdown.set_width(350)
        transport_types = sorted(self.STOPS) # List all possible types
        transport_type_dropdown.set_options("\n".join(transport_types)) # Options = List of types
        selected_transport_type = (
            transport_types.index(self.default_transport_type)
            if self.default_transport_type in transport_types
            else 0
        )
        transport_type_dropdown.set_selected(selected_transport_type) # Default, select first entry
        self.default_transport_type = transport_types[selected_transport_type]
        self.transport_type_dropdown = transport_type_dropdown
        self.controls.append(transport_type_dropdown)
        def on_transport_type_changed(_event):
            """What to do when a different value is selected"""
            names = transport_type_dropdown.get_options().splitlines()
            index = transport_type_dropdown.get_selected()
            if 0 <= index < len(names):
                selected_type = f"Type: {transport_types[index]}"
                self.default_transport_type = names[index]
                log(selected_type)
            stop_names = sorted(self.STOPS[self.default_transport_type]) # Update list of all possible stops
            stop_dropdown.set_options("\n".join(stop_names)) # Display updated list
            self.default_stop = stop_names[0]
        transport_type_dropdown.add_event_cb( # This listens to updates to the dropdown
            on_transport_type_changed, # This is the function it will run.
            lv.EVENT.VALUE_CHANGED, # When a value is changed
            None
        )

        # STOP SELECTOR
        stop_label = lv.label(self.settings_screen)
        stop_label.set_text("Stop:")
        stop_label.set_pos(75, 140)
        self.labels.append(stop_label)

        stop_dropdown = lv.dropdown(self.settings_screen)
        stop_dropdown.set_pos(200, 140)
        stop_dropdown.set_width(350)
        stop_names = sorted(self.STOPS[self.default_transport_type])
        stop_dropdown.set_options("\n".join(stop_names))

        selected_stop = (
            stop_names.index(self.default_stop)
            if self.default_stop in stop_names
            else 0
        )
        stop_dropdown.set_selected(selected_stop)
        self.default_stop = stop_names[selected_stop]
        self.stop_dropdown = stop_dropdown
        self.controls.append(stop_dropdown)
        def on_stop_changed(_event):
            """What to do when a different value is selected"""
            names = stop_dropdown.get_options().splitlines()
            index = stop_dropdown.get_selected()
            if 0 <= index < len(names):
                self.default_stop = names[index]
            log(f"Selected: {self.default_stop}")
        stop_dropdown.add_event_cb( # This listens to updates to the dropdown
            on_stop_changed, # This is the function it will run.
            lv.EVENT.VALUE_CHANGED, # When a value is changed
            None,
        )
        for dropdown in (transport_type_dropdown, stop_dropdown):
            dropdown.set_style_text_font(self.font_16, 0)
            dropdown.get_list().set_style_text_font(self.font_16, 0)

        # SAVE SETTINGS
        save_settings_button = lv.button(self.settings_screen)
        save_settings_button.set_pos(75, 260)
        save_settings_button.set_size(200, 50)
        save_settings_button.set_style_border_width(2, 0)
        self.controls.append(save_settings_button)

        save_settings_label = lv.label(save_settings_button)
        save_settings_label.set_text("SAVE")
        save_settings_label.center()
        self.labels.append(save_settings_label)

        save_settings_button.add_event_cb(
            lambda event: self.save_settings(),
            lv.EVENT.CLICKED,
            None,
        )

        # RESET BUTTON
        reset_settings_button = lv.button(self.settings_screen)
        reset_settings_button.set_pos(356, 260)
        reset_settings_button.set_size(200, 50)
        reset_settings_button.set_style_border_width(2, 0)
        self.controls.append(reset_settings_button)

        reset_settings_label = lv.label(reset_settings_button)
        reset_settings_label.set_text("RESET")
        reset_settings_label.center()
        self.labels.append(reset_settings_label)

        reset_settings_button.add_event_cb(
            lambda _event: self.reset_settings(),
            lv.EVENT.CLICKED,
            None,
        )

        # QR CODE
        legal_label = lv.label(self.settings_screen)
        legal_label.set_text("Trafiklab ToS")
        legal_label.set_pos(200, 400)
        legal_label.add_flag(lv.obj.FLAG.CLICKABLE)
        legal_label.set_ext_click_area(20)
        legal_label.add_event_cb(
            lambda _event: self.tileview.set_tile(self.qr_scr, False),
            lv.EVENT.CLICKED,
            None,
        )
        self.labels.append(legal_label)

        log("settings-screen updated")

    def create_qr_legal_screen(self):
        """Shows a QR-code for the legal-text related to Trfa"""
        self.qr_scr = self.tileview.add_tile(3, 1, lv.DIR.NONE)
        self.backgrounds.append(self.qr_scr)

        return_label = lv.label(self.qr_scr)
        return_label.set_text("< Back")
        return_label.set_pos(200, 20)
        return_label.add_flag(lv.obj.FLAG.CLICKABLE)
        return_label.set_ext_click_area(20)
        return_label.add_event_cb(
            lambda _event: self.tileview.set_tile(self.settings_screen, False),
            lv.EVENT.CLICKED,
            None,
        )
        self.labels.append(return_label)

        self.qr_image = lv.image(self.qr_scr)
        self.qr_image.set_src("S:/assets/QR_Black_On_White.png")
        self.qr_image.center()

    def create_journey_selection_screen(self):
        """Function: Create a journey selection screen"""
        self.journey_selection_screen = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT)

        # JOURNEY HEADER-LABEL
        journey_header = lv.label(self.journey_selection_screen)
        journey_header.set_text("Journey Selection")
        journey_header.set_style_text_font(self.font_28, 0)
        journey_header.align(lv.ALIGN.CENTER, 0, -150) # Place the label on the tile
        self.labels.append(journey_header)

        ## JOURNEY FROM SELECTOR
        # JOURNEY FROM LABEL
        from_label = lv.label(self.journey_selection_screen)
        from_label.set_text("From:")
        from_label.set_pos(75, 150)
        from_label.set_style_text_font(self.font_28, 0)
        self.labels.append(from_label)

        # JOURNEY FROM DROPDOWN
        from_dropdown = lv.dropdown(self.journey_selection_screen)
        from_dropdown.set_pos(200, 150)
        from_dropdown.set_width(325)
        from_dropdown.set_style_text_font(self.font_16, 0)
        from_dropdown.get_list().set_style_text_font(self.font_16, 0)
        from_names = sorted(self.STOPS["ALL"]) # List of names of stop, to be presented as options
        from_dropdown.set_options("\n".join(from_names)) # Use list above as options

        selected_from = (
            from_names.index(self.journey_from)
            if self.journey_from in from_names
            else 0) # Find default stop in list

        from_dropdown.set_selected(selected_from) # Set default stop as selected
        self.journey_from = from_names[selected_from] # Update the defaultly seleceted stop as journey_from
        self.controls.append(from_dropdown) # Add to list of controls to be recolored
        def on_from_changed(_event): # Update journey_from when dropdown changes
            """What to do when a different value is selected"""
            names = from_dropdown.get_options().splitlines()
            index = from_dropdown.get_selected()
            if 0 <= index < len(names):
                self.journey_from = names[index]
            log(f"Journey From: {self.journey_from}")
        from_dropdown.add_event_cb( # This listens to updates to the dropdown
            on_from_changed, # This is the function it will run.
            lv.EVENT.VALUE_CHANGED, # When a value is changed
            None,
        )

        ## JOURNEY TO SELECTOR
        # JOURNEY LABEL
        to_label = lv.label(self.journey_selection_screen)
        to_label.set_text("To:")
        to_label.set_pos(75, 250)
        to_label.set_style_text_font(self.font_28, 0)
        self.labels.append(to_label)

        # JOURNEY TO DROPDOWN
        to_dropdown = lv.dropdown(self.journey_selection_screen)
        to_dropdown.set_pos(200, 250)
        to_dropdown.set_width(325)
        to_dropdown.set_style_text_font(self.font_16, 0)
        to_dropdown.get_list().set_style_text_font(self.font_16, 0)
        to_names = sorted(self.STOPS["ALL"])
        to_dropdown.set_options("\n".join(to_names))

        selected_to = (
            to_names.index(self.journey_to)
            if self.journey_to in to_names
            else 0
        )
        to_dropdown.set_selected(selected_to)
        self.journey_to = to_names[selected_to]
        self.controls.append(to_dropdown)
        def on_to_changed(_event): # Update journey_to when dropdown changes
            """What to do when a different value is selected"""
            names = to_dropdown.get_options().splitlines()
            index = to_dropdown.get_selected()
            if 0 <= index < len(names):
                self.journey_to = names[index]
            log(f"Journey To: {self.journey_to}")
        to_dropdown.add_event_cb( # This listens to updates to the dropdown
            on_to_changed, # This is the function it will run.
            lv.EVENT.VALUE_CHANGED, # When a value is changed
            None,
        )
        #### Add for potential Dark/Light mode
        self.backgrounds.append(self.journey_selection_screen)
        log("journey-screen created")

    def create_journey_screen(self):
        """Creates the screen for displaying the journeys"""
        self.journey_screen = self.tileview.add_tile(0, 0, lv.DIR.RIGHT)

        self.journey_screen_label = lv.label(self.journey_screen)
        self.journey_screen_label.set_style_text_font(self.font_28, 0)
        self.journey_screen_label.set_text("Reseskärm")
        self.journey_screen_label.align(lv.ALIGN.CENTER, 0, -180)
        self.backgrounds.append(self.journey_screen)
        self.labels.append(self.journey_screen_label)

    def create_ui(self):
        'Function: Creates UI'
        #api_data = read_data(False) ## IF TRUE, ONLY USE TEST-DATA INSTEAD (i.e. don't use ACTUAL data)
        self.tileview = lv.tileview(lv.screen_active()) ## Creates frame to add tiles to
        self.tileview.set_size(600, 450) ## That is the size 600 in x and 450 in y
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF) ## Scrollbar is that thing on your right that you can grab and scroll.
        self.read_settings() ## Reads settings from file.
        self.create_title_screen() ## Creation of Title-Screen.
        self.create_qr_legal_screen() ## Create QR-screen
        self.create_journey_selection_screen() ## Create Journey Selection Screen
        self.create_journey_screen() ## Create subsequent Journey Screen
        self.settings_screen = self.tileview.add_tile(3, 0, lv.DIR.LEFT | lv.DIR.RIGHT) # Create a blank settings-screen on our tileview
        self.backgrounds.append(self.settings_screen)
        self.create_settings_screen() ## Placeholder creation of Settings-screen
        self.dep_scr = self.tileview.add_tile(4, 0, lv.DIR.LEFT) # Create a placeholder departure screen
        self.backgrounds.append(self.dep_scr)
        self.tileview.set_tile(self.title_screen, False)

        self.previous_tile = self.tileview.get_tile_active()
        self.tileview.add_event_cb(
            self.on_tile_changed,
            lv.EVENT.VALUE_CHANGED,
            None,
        )

        #### Add for potential Dark/Light mode
        self.backgrounds.append(self.tileview)

        self.apply_colors()
        log("UI created")

    @staticmethod
    def connect_wifi():
        'Function: Connects to WiFi'
        networks = WIFI_LIST or [(WIFI_SSID, WIFI_PASSWORD)]

        station = network.WLAN(network.STA_IF)
        station.active(True)

        for ssid, password in networks:
            log(f"Connection to Wi-Fi SSID: {ssid}")

            try:
                station.disconnect()
                station.connect(ssid, password)
                started = time.ticks_ms()

                while (
                    not station.isconnected()
                    and time.ticks_diff(time.ticks_ms(), started) < 15_000
                ):
                    time.sleep_ms(250)
                if station.isconnected():
                    log("Wi-Fi connected")
                    return ssid

                log(f"Wi-Fi connection timed out: {ssid}")
            except OSError as error:
                log(f"Wifi connection failed for {ssid}: {error}")
        station.disconnect()
        log("Could not connect to any configured network")
        return False


try:
    # print("Starting application")
    app = Application()
except Exception as error:
    log("FATAL: %r" % (error,))
    sys.print_exception(error) # pylint: disable=no-member
    raise
