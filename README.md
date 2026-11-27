# L.I.G.M.A.B

## Introduction

L.I.G.M.A.B is a public transport application developed for the LilyGo ESP32-T4-S3 using MicroPython, LVGL and PlatformIO. The application helps users find public transport departures and plan journeys by bus, train and ferry in the Karlskrona area. 

## Getting started

The student workflow works on Windows, Linux, and macOS. The first PlatformIO
setup can take several minutes while tools are installed.

### Prerequisites

- Visual Studio Code
- PlatformIO IDE extension
- LilyGO ESP32-T4-S3 (for hardware deployment)
- USB cable (for hardware deployment)
- Wi-Fi connection for live data
- Valid Trafiklab and ResRobot API keys

The supplied firmware already contains MicroPython and LVGL. No separate compilation of MicroPython or LVGL is required.

### Installation

#### PlatformIO

1. Install Visual Studio Code
   * Visit [Visual Studio Code's website](https://code.visualstudio.com/download) and download the latest version or use the package manager of your system.
   * Run `Visual Studio Code` and follow the steps.
2. Install the correct extension.
   * Head over to the extensions tab on your left.
   * Search for ["PlatformIO IDE"](https://marketplace.visualstudio.com/items?itemName=platformio.platformio-ide) and install it.
3. Clone the GitHub repository.
4. Open the cloned repository in Visual Studio Code.
5. Configure Wi-Fi credentials and API keys as described below.

### Linux: Serial Port Access

Windows and macOS need no extra setup. On Linux the board's serial port is
owned by a system group, so PlatformIO cannot open it until you grant access.
Install the PlatformIO udev rules once:

```bash
curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules \
  | sudo tee /etc/udev/rules.d/99-platformio-udev.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then unplug and reconnect the board. If the port is still unreadable, add
yourself to the group that owns it (`ls -l /dev/ttyACM0` shows which):
`dialout` on Debian/Ubuntu, `uucp` on Arch.

```bash
sudo usermod -aG dialout $USER   # or uucp
```

Log out and back in for the group change to take effect.

### Wi-Fi Configuration

The T4-S3 has built-in Wi-Fi, but it cannot connect to eduroam. Use another
network or a phone hotspot.

Add or modify the `project/secrets.py` file, then set the SSID
(network name) and password.

```python
WIFI_SSID      = "SSID"
WIFI_PASSWORD  = "PWD"
```

Never commit real credentials to GitHub. `project/secrets.py` is excluded by
the supplied `.gitignore`.

### API Configuration 

To retrieve live public transport information, valid API keys must be added to project/secrets.py:

```python
TRAFIKLAB_API_KEY = "YOUR API KEY"
RESROBOT_API_KEY = "YOUR_API_KEY"
```
Never commit real API keys or Wi-Fi credentials to GitHub.

## Building and Running

### Running on the Simulator

The application can also be run on a desktop computer without an ESP32 device.

For installation and usage instructions, see the [desktop simulator setup](t4s3-simulator/README.md).

### Running on ESP32

1. Open the locally cloned repository with Visual Studio Code
    * If the "Do you trust the authors of the files in this folder?" dialog appears, click on "Yes, I trust the authors"
2. Open up the file `project/main.py`
3. Connect your ESP32 to your computer via a USB cable.
4. Open the PlatformIO tab in the left sidebar, expand
   **Project Tasks > t4s3-micropython > Custom**, and run **Deploy complete
   project**. This flashes the MicroPython firmware and your Python files in
   one step, and is what the Upload button runs too.

Once the board has firmware on it, **Flash Python application** is faster for
everyday work: it writes only your `project/` files and leaves the firmware
alone.

![PlatformIO tasks for this project](./assets/screenshot.png)

---

## Application Features

- Display real-time public transport departures.
- Display route numbers, destinations, arrival times and delays.
- Automatically refresh departure information every 60 seconds.
- Filter and search for stops.
- Plan journeys between two selected stops.
- Sort journey suggestions by earliest arrival time.
- Switch between dark and light mode.
- Save and restore user settings.
- Access Trafiklab's Terms of Service through a QR code.

## Screen Descriptions

### 0. L.I.G.M.A.B screen:

Displays the application name, group number, group members and application version.

### 1. Settings screen:

Allows the user to select a transport type and a stop. 

The user can switch between dark and light mode, save their current settings or restore previously saved settings. 

Trafiklab's Terms of Service can be accessed by selecting "Trafiklab ToS" and scanning the displayed QR code.

### 2. Departure screen:

Displays upcoming departures from the selected stop, including: 

- Route number
- Transport type
- Destination
- Estimated time of arrival (ETA)
- Delays

Departure information is automatically refreshed every 60 seconds while the screen is active.

### -1. Journey Selection Screen:

Allows the user to select a departure stop (From) and a destination stop (To).

Stops can be selected using dropdown menus or searched for using the on-screen keyboard.

### -2. Top 5 Journeys:

Displays journey suggestions between the selected departure and destination stops.

Each journey contains departure and arrival times, total travel duration and individual travel segments, including transfers and walking distances where applicable.

Journeys are sorted by earliest arrival time.

## Navigation

The user navigates between the main screens by swiping horizontally on the touchscreen.

The QR code screen is accessed through the Settings Screen.

## Trafiklab API Integration

The application uses two APIs to retrieve public transport information:

- Trafiklab Realtime API: Provides departure information, destinations, scheduled and real-time departure times, delays and cancellations.

- ResRobot API: Provides journey suggestions between selected stops, including travel times, transfers and walking segments.

The application uses STOPS.json to associate stop names with their corresponding stop IDs.

### Data Attribution

Public transport data is provided by [Trafiklab](https://www.trafiklab.se/) through the Trafiklab Realtime API and ResRobot API.

## Project structure

Device application code and assets belong in the [**/project**](project/main.py)
folder, which is copied recursively into the device filesystem image.
Desktop application tests belong in the top-level `tests/` folder so they
are not packaged or deployed. Selected board support files are added from
`support/` separately.

| File / Directory | Description |
| --- | --- |
| `project/main.py` | Handles the user interface, navigation, settings and Wi-Fi connection. |
| `project/data.py` | Retrieves, processes and sorts public transport data. |
| `project/STOPS.json` | Contains stop names and their corresponding IDs. |
| `project/secrets.py` | Contains Wi-Fi credentials and API keys. |
| `t4s3-simulator/` | Contains the desktop simulator. |
| `tests/` | Contains automated application tests. |
| `support/` | Contains board support files. |

## Quality Assurance

The project uses several quality assurance practices:

- Code reviews through GitHub pull requests.
- Manual testing using the desktop simulator.
- Manual testing on the ESP32 device.
- Automated testing.

## Troubleshooting

### The screen still shows the old interface, and touch does nothing

The board is probably still in upload mode. Tap **RESET/RST once**. 
A retained image on the AMOLED does not mean the application is running.

### Upload cannot connect

1. Stop PlatformIO Monitor with `Ctrl+C`.
2. Disconnect and reconnect the USB cable if the port is locked.
3. Repeat the BOOT/RESET upload-mode sequence.
4. Start Upload again.

On Linux, `Permission denied` on `/dev/ttyACM0` means the udev rules above are
not installed.

### Upload stops at "Stub running... No serial data received"

The board flashes over the ESP32-S3's built-in USB port, where the baud rate is
virtual and cannot be renegotiated. Check that `upload_speed` in
`platformio.ini` is still `115200`; raising it produces exactly this error.

After a failed upload the board may not restart on its own. Press **RESET**
by hand before retrying.

### Upload fails with "Invalid head of packet"

This appears once a Python application is already running on the board: it
prints to the same USB port the uploader needs, and the automatic reset into
upload mode cannot interrupt it. Enter upload mode by hand instead.

1. Hold **BOOT**.
2. Tap **RESET**.
3. Release **BOOT**.
4. Start the upload task immediately.

The board stays in upload mode afterwards, so press **RESET** once when the
upload finishes to start your application.

Close PlatformIO Monitor first if it is running; anything else holding the
serial port causes the same error.

### The screen is black

Open PlatformIO Monitor after resetting. Startup errors are printed at 115200
baud and also stored as `/debug.log` on the device.

### LilyGo tutorial

Visit LilyGO [link](https://github.com/Xinyuan-LilyGO/LilyGo-AMOLED-Series)

## Features

### Start-up

- [X] US1.1: As a user, I want to see a starting screen displaying the project name, current program
version, group number, and members' names.
- [X] US1.2B: As a user, I want to see the departure screen showing departure data: departure time,
line, destination, and departure status for any destinations in Karlskrona using live data from
Trafiklab (https://www.trafiklab.se/sv/api/our-apis/trafiklab-realtime-apis/).

### Tile Navigation & Access

- [X] US2.1: As a user, I want to navigate between different screens by sliding a finger over the
touchscreen.

### Settings & Configuration

- [X] US3.1: As a user, I want to access a settings screen.
- [X] US3.2C: As a user, I want to search and select different stops for US1.2B.
- [X] US3.3: As a user, I want to select a transport type (bus, train, ferry, and all) using a dropdown.
- [X] US3.4: As a user, I want to save my current settings as the default and have them restored when
the device restarts.
- [X] US3.5: As a user, I want to reset my current settings to the stored default settings.

### Real-time Data Update

- [X] US4.1: As a user, I want the live departure data to update automatically in 60 seconds.
- [X] US4.2B: As a user, I want to manually refresh the departure data with a button in the settings
screen.
- [X] US4.3: As a user, I want to see the current Wi-Fi connection and live data status on the settings
screen.

### Journey Selection

- [X] US5.1: As a user, I want to access a journey selection screen.
- [X] US5.2B: As a user, I want to search for and select a starting stop and a final destination stop for US5.3.
- [X] US5.3B: As a user, I want to see the top matching journey, based on arrival time to the final
destination, that shows the departure time for each intermediate stop where I must change
transportation.

## Non-Functional Requirements (NFRs)

- [X] NF1: The code must follow a suitable coding standard.
- [X] NF2: The code must be well-documented, including inline comments and Markdown
documentation.
- [X] NF3: The project must follow the terms and conditions of the Trafiklab data source. You should
clearly provide the attribution.
- [X] NF4: The BTH/LILYGO skeleton source files must remain unchanged. However, you can design
modular architecture.
- [X] NF5: You should apply a suitable quality assurance strategy (e.g., code review, manual testing,
and/or automated testing) and document this process in your GitHub repository.

----------------------------------------------------




