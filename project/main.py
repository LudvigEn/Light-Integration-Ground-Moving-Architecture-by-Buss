import sys # Access system utilities, including exception reporting
import time # Provide timing and delay functions

import lvgl as lv # Import the LVGL graphics library
import network # Access the boards network interface

from board_lvgl import start_board # Import the function that initializes the display and touch hardware
from debug_log import log # Import the applications logging function

from secrets import WIFI_SSID, WIFI_PASSWORD # Load the Wi-Fi network name and password

from data import * # Load the data-processing module

VERSION = 0.3 # Version-control

class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()
        self.dark_mode = True # Dark mode toggle, default on
        self.backgrounds = [] # List of all backgrounds, for toggling dark-mode
        self.borders = [] # List of all borders (like around boxes), for toggling dark-mode
        self.labels = [] # List of all labels, for toggling dark-mode
        self.controls = [] # List of all controls (buttons/dropdowns), for toggling dark-mode
        self.default_stop = "Campus Gräsvik"
        self.default_transport_type = "BUS"
        self.STOPS = {
                        "BUS":{
                            "Campus Gräsvik": "740032188",
                            "Karlskrona Centralstation": "740000230"
                        },
                        "TRAIN":{}
                    }
        self.connect_wifi() # Function to connect to wifi
        self.create_ui() # Function to trigger creation of UI
        log("student application ready")

    def save_settings(self):
        """Function: Save settings to file."""
        with open("settings.txt", "w", encoding="utf-8") as file:
            to_write = f"{self.default_stop}\n{self.default_transport_type}\n{self.dark_mode}"
            file.write(to_write)
            log_written = f"Saved: \n{to_write}"
            log(log_written)

    def read_settings(self):
        """If a settings.txt file is present, read the data from it
        If there are not 3 lines of text in it; revert to defaults
        """
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
        self.dark_mode = lines[2]

    def apply_colors(self):
        """Function: Actually change label and tile color"""
        background_color = lv.color_hex(0x000000 if self.dark_mode else 0xFFFFFF) # Background color, if Dark-mode: black, else white
        foreground_color = lv.color_hex(0xFFFFFF if self.dark_mode else 0x000000) # Foreground (topmost layer) color, if Dark-mode: white, else black

        for widget in self.backgrounds: # For all backgrounds
            widget.set_style_bg_opa(lv.OPA.COVER, 0) # Make the background fully opaque (ogenomskinlig)
            widget.set_style_bg_color(background_color, 0) # Change background color to background_color

        for widget in self.borders: # For all borders
            widget.set_style_bg_opa(lv.OPA.COVER, 0) # Make the background fully opaque (ogenomskinlig)
            widget.set_style_bg_color(foreground_color, 0) # Change foreground color to foreground_color

        for label in self.labels: # For all labels
            label.set_style_text_color(foreground_color, 0) # Change foreground color to foreground_color

        for control in self.controls:
            control.set_style_bg_opa(lv.OPA.COVER, 0)
            control.set_style_bg_color(background_color, 0)
            control.set_style_text_color(foreground_color, 0)
            control.set_style_border_color(foreground_color, 0)

    def toggle_dark_side(self, _event):
        """Function: Toggles dark-mode on tile2..."""
        self.dark_mode = self.dark_mode_switch.has_state(lv.STATE.CHECKED) ## Dark mode = State of slider
        self.apply_colors() ## Apply colors to Backgrounds, Borders and Labels

    def create_title_screen(self):
        """Function: Startup-screen"""
        self.title_screen = self.tileview.add_tile(0, 0, lv.DIR.RIGHT) # Create a screen on our tileview

        # Create labels for title-screen
        self.title_screen_label = lv.label(self.title_screen) # Add a label to the Title screen
        self.title_screen_label_group_name = lv.label(self.title_screen) # Add a label to the Title screen
        self.title_screen_label_version = lv.label(self.title_screen) # Add a label to the Title screen

        # Heading
        self.title_screen_label.set_text("L.I.G.M.A.B") # Set label to the name of the project
        self.title_screen_label.set_style_text_font(lv.font_montserrat_28, 0) # Set font of the label
        self.title_screen_label.align(lv.ALIGN.CENTER, 0, -100) # Place the label on the tile

        ## Group Name
        self.title_screen_label_group_name.set_text("Group 15\nLudvig En, Isac Aubert, Gösta Palmqvist,\nMelker Ruben Saar, Bastian Gralén") # Set label to the name of the members
        self.title_screen_label_group_name.set_style_text_font(lv.font_montserrat_16, 0) # Set font of the label
        self.title_screen_label_group_name.center() # Place the label on the tile

        ### Version
        self.title_screen_label_version.set_text(f"Version:{VERSION}") # Set label to the version of the project
        self.title_screen_label_version.set_style_text_font(lv.font_montserrat_16, 0) # Set font of the label
        self.title_screen_label_version.align(lv.ALIGN.CENTER, 0, 100) # Place the label on the tile

        #### Add for potential Dark/Light mode
        self.backgrounds.append(self.title_screen) # Add to list of all backgrounds
        self.labels.append(self.title_screen_label) # Add to list of all labels
        self.labels.append(self.title_screen_label_group_name) # Add to list of all labels
        self.labels.append(self.title_screen_label_version) # Add to list of all labels
        log("title-screen created")

    def clear_departures(self):
        """Clears existing departure data to be replaced with new data."""
        def belongs_to_departures(widget):
            parent = widget.get_parent()
            while parent is not None:
                if parent == self.dep_scr:
                    return True
                parent = parent.get_parent()
            return False

        for widgets in (self.backgrounds, self.borders, self.labels, self.controls):
            widgets[:] = [
                widget for widget in widgets
                if not belongs_to_departures(widget)
            ]
        self.dep_scr.clean()
        # self.dep_scr.scroll_to_y(0, )

    def on_tile_changed(self, event):
        """To update dep"""
        if event.get_target() != self.tileview:
            return
        if self.tileview.get_tile_active() != self.dep_scr:
            return

        self.clear_departures()

        transport_types = list(self.STOPS)
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
                    stop = read_data(stop_id)
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
        if stop is not None:
            self.create_departure_screen(stop)
        else:
            error_label = lv.label(self.dep_scr)
            error_label.set_text(message)
            self.labels.append(error_label)
        self.apply_colors()

    def create_departure_screen(self, stop):
        """Function: Show departures on a specific stop."""

        ## Name of bus-stop
        header = lv.label(self.dep_scr) # Add a label to the Departure screen
        header.set_text(stop.name) # Name of stop as header
        header.set_width(450) # Set width of label
        header.set_pos(75, 10) # Fixed position of label
        header.set_style_text_font(lv.font_montserrat_28, 0) # Set font of the label
        self.labels.append(header) # Add to list of labels

        border_width = 2 # Thickness of box edges
        rows = [("Route", "Destination", "ETA", "Delay")]
        column_widths = [65, 185, 100, 100]

        ## For each departure, we will have a row with 3 columns; Route, Direction and Time
        for departure in stop.departures:
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
                row.set_size(450, 60)
                row.set_pos(75, 55 + row_index * 70)
                self.backgrounds.append(row)

                x = 0

                for width, value in zip(column_widths, values):
                    ## Box in row
                    outline = lv.obj(row)
                    outline.set_size(width, 60)
                    outline.set_pos(x, 0)
                    self.borders.append(outline)

                    inner = lv.obj(outline)
                    inner.set_size(
                        width - 2 * border_width,
                        60 - 2 * border_width,
                    )
                    inner.set_pos(border_width, border_width)
                    self.backgrounds.append(inner)

                    label = lv.label(inner)
                    label.set_width(width - 10)
                    label.set_style_text_font(lv.font_montserrat_16, 0)
                    label.set_text(str(value) if value is not None else "")
                    label.center()
                    self.labels.append(label)

                    x += width
        log("departure-screen updated")

    def create_settings_screen(self):
        """Function: Create a settings screen"""
        self.settings_screen = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT) # Create a screen on our tileview

        settings_header = lv.label(self.settings_screen)
        settings_header.set_pos(30, 20)
        settings_header.set_text("Settings")
        self.labels.append(settings_header)

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
        transport_types = list(self.STOPS) # List all possible types
        transport_type_dropdown.set_options("\n".join(transport_types)) # Options = List of types
        transport_type_dropdown.set_selected(0) # Default, select first entry
        self.transport_type_dropdown = transport_type_dropdown
        self.controls.append(transport_type_dropdown)
        def on_transport_type_changed(event):
            """What to do when a different value is selected"""
            t_index = transport_type_dropdown.get_selected()
            selected_type = f"Type: {transport_types[t_index]}"
            self.default_transport_type = transport_types[t_index]
            stop_names = list(self.STOPS[self.default_transport_type]) # Update list of all possible stops
            stop_dropdown.set_options("\n".join(stop_names)) # Display updated list
            log(selected_type)
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
        stop_names = list(self.STOPS[self.default_transport_type])
        stop_dropdown.set_options("\n".join(stop_names))
        stop_dropdown.set_selected(0)
        self.stop_dropdown = stop_dropdown
        self.controls.append(stop_dropdown)
        def on_stop_changed(event):
            """What to do when a different value is selected"""
            index = stop_dropdown.get_selected()
            self.default_stop = stop_names[index]
            selected_log = f"Selected: {stop_names[index]}"
            log(selected_log)
        stop_dropdown.add_event_cb( # This listens to updates to the dropdown
            on_stop_changed, # This is the function it will run.
            lv.EVENT.VALUE_CHANGED, # When a value is changed
            None,
        )

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
        # # RESET SETTINGS
        # reset_settings_button = lv.button(self.settings_screen)
        # reset_settings_button.set_pos(280, 260)
        # reset_settings_button.set_size(200, 50)
        # reset_settings_button.set_style_border_width(2, 0)
        # self.controls.append(reset_settings_button)

        # reset_settings_label = lv.label(reset_settings_button)
        # reset_settings_label.set_text("RESET")
        # reset_settings_label.center()
        # self.labels.append(reset_settings_label)

        # reset_settings_button.add_event_cb(
        #     self.save_settings(),
        #     lv.EVENT.CLICKED,
        #     None,
        # )


        #### Add for potential Dark/Light mode
        self.backgrounds.append(self.settings_screen)
        log("settings-screen created")

    def create_ui(self):
        'Function: Creates UI'
        #api_data = read_data(False) ## IF TRUE, ONLY USE TEST-DATA INSTEAD (i.e. don't use ACTUAL data)
        self.tileview = lv.tileview(lv.screen_active()) ## Creates frame to add tiles to
        self.tileview.set_size(600, 450) ## That is the size 600 in x and 450 in y
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF) ## Scrollbar is that thing on your right that you can grab and scroll.
        self.read_settings()
        self.create_title_screen() ## Creation of Title-Screen
        self.create_settings_screen() ## Placeholder creation of Settings-screen
        self.dep_scr = self.tileview.add_tile(2, 0, lv.DIR.LEFT) # Create a placeholder departure screen
        self.backgrounds.append(self.dep_scr)

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
        log("connecting to Wi-Fi SSID: " + WIFI_SSID)
        station = network.WLAN(network.STA_IF)
        station.active(True)
        station.connect(WIFI_SSID, WIFI_PASSWORD)
        started = time.ticks_ms()
        while (not station.isconnected() and
               time.ticks_diff(time.ticks_ms(), started) < 15_000):
            time.sleep_ms(250)
        log("Wi-Fi connected" if station.isconnected()
            else "Wi-Fi could not connect (timeout)")


try:
    app = Application()
except Exception as error:
    log("FATAL: %r" % (error,))
    sys.print_exception(error)
    raise
