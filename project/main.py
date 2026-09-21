import sys # Access system utilities, including exception reporting
import time # Provide timing and delay functions

import lvgl as lv # Import the LVGL graphics library
import network # Access the boards network interface

from board_lvgl import start_board # Import the function that initializes the display and touch hardware
from debug_log import log # Import the applications logging function

from secrets import WIFI_SSID, WIFI_PASSWORD # Load the Wi-Fi network name and password

from data import * # Load the data-processing module

VERSION = 0.2 # Version-control

class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()
        self.dark_mode = True # Dark mode toggle, default on
        self.backgrounds = [] # List of all backgrounds, for ease of access
        self.borders = [] # List of all borders (like around boxes), for ease of access
        self.labels = [] # List of all labels, for ease of access
        self.connect_wifi() # Function to connect to wifi
        self.create_ui() # Function to trigger creation of UI
        log("student application ready")

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

    def open_departures(self, stop):
        """Function: Opens the selected departure-screen"""
        self.remove_screen("dep_scr") ## Removes the "old" Departure-screen
        self.create_departure_screen(stop) ## Creates a Departure-screen from a Stop
        self.apply_colors() ## Dark/Light-mode
        self.tileview.set_tile(self.dep_scr, lv.ANIM.OFF) ## Focus on a Departure tile

    def open_stops(self, route):
        """Show the laded stops served by the selected route."""
        self.tileview.set_tile(self.routes_screen, lv.ANIM.OFF) ## Focus on Routes-screen

        self.remove_screen("dep_scr") ## Remove "old" Departure-screen
        self.remove_screen("route_scr") ## Remove "old" Stop-screen

        self.create_stops_screen(route, self.stops) ## Create new Stop-screen
        self.apply_colors() ## Dark/Light-mode
        self.tileview.set_tile(self.route_scr, lv.ANIM.OFF) ## Focus on Stop-screen

    def toggle_dark_side(self, _event):
        """Function: Toggles dark-mode on tile2..."""
        self.dark_mode = self.dark_mode_switch.has_state(lv.STATE.CHECKED) ## Dark mode = State of slider
        self.apply_colors() ## Apply colors to Backgrounds, Borders and Labels

    def remove_screen(self, attribute):
        """Delete a screen no longer focused"""
        if not hasattr(self, attribute):
            return
        screen = getattr(self, attribute)

        def belongs_to_screen(widget):
            while widget is not None:
                if widget == screen:
                    return True
                widget = widget.get_parent()
            return False

        for widgets in (self.backgrounds, self.borders, self.labels):
            widgets[:] = [
                widget for widget in widgets
                if not belongs_to_screen(widget)
            ]

        screen.delete()
        delattr(self, attribute)

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

    def create_departure_screen(self, stop):
        """Function: Show departures on a specific stop."""
        self.dep_scr = self.tileview.add_tile(4, 0, lv.DIR.LEFT) # Create a screen on our tileview

        ## Name of bus-stop
        header = lv.label(self.dep_scr) # Add a label to the Departure screen
        header.set_text(stop.name) # Name of stop as header
        header.set_width(450) # Set width of label
        header.set_pos(75, 10) # Fixed position of label
        header.set_style_text_font(lv.font_montserrat_28, 0) # Set font of the label

        border_width = 2 # Thickness of box edges

        ## For each departure, we will have a row with 3 columns; Route, Direction and Time
        for row_index, departure in enumerate(stop.departures):
            row = lv.obj(self.dep_scr) # Create a box
            row.set_size(450, 60) # That is the width of the entire screen and 60 high
            row.set_pos(75, 55 + row_index * 70) # And which Y-postition depends on which row it is.

            #### Add for potential Dark/Light mode
            self.backgrounds.append(row)

            dep_timestamp = departure.realtime if departure.realtime else departure.scheduled # Realtime if realtime exists, else scheduled
            dep_time = dep_timestamp[11:19] # As it's a timestamp, we only want the HH:MM:SS part, i.e. excluding the date.

            columns = [ # The 3 columns that will be shown on the departure screen
                (50, departure.route.designation), # Route
                (250, departure.route.direction), # Direction ()
                (150, dep_time) # If delay -> realtime, else scheduled
            ]

            x = 0
            for width, value in columns:
                outline = lv.obj(row) # For each value, we create a box
                outline.set_size(width, 60) # That is of a variable width (Route does not need to be big)
                outline.set_pos(x, 0) # And the position is dependent on the size of the box

                #### Add for potential Dark/Light mode
                self.borders.append(outline)

                inner = lv.obj(outline)
                inner.set_size(
                    width - 2 * border_width,
                    60 - 2 * border_width
                )
                inner.set_pos(border_width, border_width)
                self.backgrounds.append(inner)

                label = lv.label(inner) # We create a label inside the box
                label.set_width(width - 10) # Width-limitation on our label (so it doesn't spill over)
                label.set_text(str(value) if value is not None else "") # Put values on labels in boxes
                label.center() # Center on middle of the box
                x += width # And then move on the the next box

                #### Add for potential Dark/Light mode
                self.labels.append(label)


        #### Add for potential Dark/Light mode
        self.labels.append(header) # Add to list of labels
        self.backgrounds.append(self.dep_scr) # Add to list of backgrounds
        log("departure-screen created")

    def create_routes_screen(self, stops):
        """Function: Show all routes."""
        self.stops = stops
        self.routes_screen = self.tileview.add_tile(2, 0, lv.DIR.LEFT) # Create a screen on our tileview
        self.backgrounds.append(self.routes_screen)

        ## Name of route.
        header = lv.label(self.routes_screen) # Add a label to the Departure screen
        header.set_text(f"Routes:") # Name of stop as header
        header.set_width(450) # Set width of label
        header.set_pos(75, 10) # Fixed position of label
        header.set_style_text_font(lv.font_montserrat_28, 0) # Set font of the label
        self.labels.append(header) # Add to list of labels

        border_width = 2 # Thickness of box edges

        routes = {}

        for stop in stops:
            for departure in stop.departures:
                route = departure.route
                if route.designation:
                    routes[route.designation] = route

        for row_index, designation in enumerate(sorted(routes)):
            route = routes[designation]

            row_box = lv.obj(self.routes_screen) # For each value, we create a box
            row_box.set_size(450, 60) # That stretches the entire screen
            row_box.set_pos(75, 55 + row_index * 70) # And the position is dependent on the height of
            row_box.set_style_pad_all(0, 0)
            row_box.set_style_border_width(0, 0)
            self.borders.append(row_box)

            box_inner = lv.obj(row_box)
            box_inner.set_size(
                450 - 2 * border_width,
                60 - 2 * border_width
            )
            box_inner.set_pos(border_width, border_width)
            box_inner.set_style_pad_all(0, 0)
            box_inner.set_style_border_width(0, 0)
            self.backgrounds.append(box_inner)

            box_inner.add_flag(lv.obj.FLAG.CLICKABLE)
            box_inner.add_event_cb(
                lambda event, selected_route=route: self.open_stops(selected_route),
                lv.EVENT.CLICKED,
                None
            )
            label = lv.label(box_inner)
            label.remove_flag(lv.obj.FLAG.CLICKABLE)
            label.set_width(430)
            label.set_text(f"Route: {designation}")
            label.center()
            self.labels.append(label)
        log("routes-screen created")

    def create_stops_screen(self, route, stops):
        """Function: Show all stops on a specific route."""
        self.route_scr = self.tileview.add_tile(3, 0, lv.DIR.LEFT) # Create a screen on our tileview
        self.backgrounds.append(self.route_scr)

        ## Name of route.
        header = lv.label(self.route_scr) # Add a label to the Departure screen
        header.set_text(f"Route: {route.designation}") # Name of stop as header
        header.set_width(450) # Set width of label
        header.set_pos(75, 10) # Fixed position of label
        header.set_style_text_font(lv.font_montserrat_28, 0) # Set font of the label
        self.labels.append(header)

        border_width = 2 # Thickness of box edges

        route_stops = [
            stop for stop in stops
            if any(
                departure.route.designation == route.designation
                for departure in stop.departures
            )
        ]
        ## For each stop, we will have a row with each stop
        for row_index, stop in enumerate(route_stops):
            row_box = lv.obj(self.route_scr) # For each value, we create a box
            row_box.set_size(450, 60) # That stretches the entire screen
            row_box.set_pos(75, 55 + row_index * 70) # And the position is dependent on the height of
            row_box.set_style_pad_all(0, 0)
            row_box.set_style_border_width(0, 0)
            self.borders.append(row_box)

            box_inner = lv.obj(row_box)
            box_inner.set_size(
                450 - 2 * border_width,
                60 - 2 * border_width
            )
            box_inner.set_pos(border_width, border_width)
            box_inner.set_style_pad_all(0, 0)
            box_inner.set_style_border_width(0, 0)
            self.backgrounds.append(box_inner)

            box_inner.add_flag(lv.obj.FLAG.CLICKABLE)
            box_inner.add_event_cb(
                lambda event, selected_stop=stop: self.open_departures(selected_stop),
                lv.EVENT.CLICKED,
                None
            )
            label = lv.label(box_inner)
            label.remove_flag(lv.obj.FLAG.CLICKABLE)
            label.set_width(430)
            label.set_text(stop.name)
            label.center()
            self.labels.append(label)
        log("stops-screen created")

    def create_settings_screen(self):
        """Function: Create a settings screen"""
        self.settings_screen = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT) # Create a screen on our tileview

        # self.settings_screen_label = lv.label(self.settings_screen) # We label on settings-screen
        # self.settings_screen_label.set_text("I SHALL BECOME SETTINGS") # That says something (for now)
        # self.settings_screen_label.set_style_text_font(lv.font_montserrat_28, 0) # With this font
        # self.settings_screen_label.center() # In the center of the tile
        # self.settings_screen.add_flag(lv.obj.FLAG.CLICKABLE) # The settings-screen is clickable (for now)
        # self.settings_screen.add_event_cb(
        #     self.on_tile2_clicked, lv.EVENT.CLICKED, None # Create an event if user clicks on tile
        # )
        dark_mode_header = lv.label(self.settings_screen)
        dark_mode_header.set_pos(300, 20)
        dark_mode_header.set_text("Settings")
        dark_mode_label = lv.label(self.settings_screen)
        dark_mode_label.set_text("Dark side")
        dark_mode_label.set_pos(75, 80)
        self.labels.append(dark_mode_label)
        self.labels.append(dark_mode_header)

        self.dark_mode_switch = lv.switch(self.settings_screen)
        self.dark_mode_switch.set_pos(250, 75)
        if self.dark_mode:
            self.dark_mode_switch.add_state(lv.STATE.CHECKED)

        self.dark_mode_switch.add_event_cb(
            self.toggle_dark_side,
            lv.EVENT.VALUE_CHANGED,
            None
        )



        #### Add for potential Dark/Light mode
        self.backgrounds.append(self.settings_screen)
        log("settings-screen created")

    def create_ui(self):
        'Function: Creates UI'
        api_data = read_data(False) ## IF TRUE, ONLY USE TEST-DATA INSTEAD (i.e. don't use ACTUAL data)
        self.tileview = lv.tileview(lv.screen_active()) ## Creates frame to add tiles to
        self.tileview.set_size(600, 450) ## That is the size 600 in x and 450 in y
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF) ## Scrollbar is that thing on your right that you can grab and scroll.

        self.create_title_screen() ## Creation of Title-Screen
        self.create_settings_screen() ## Placeholder creation of Settings-screen
        self.create_routes_screen(api_data) ## Screen with list of Routes.


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
