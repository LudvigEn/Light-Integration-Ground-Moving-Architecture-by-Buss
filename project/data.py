"""Module to fetch, and return data"""
import json
from secrets import API_KEY # pylint:disable=no-name-in-module
import requests
try:
    from debug_log import log
except ImportError:
    def log(message):
        """Print diagnostics when the device logger is unavailable"""
        print(message)

class Route:
    """Data on Route (Linje) -granularity
    """
    def __init__(self):
        self.designation: str = None
        self.direction: str = None
        self.origin: str = None
        self.destination: str = None
        self.stops: list[Stop] = None
        self.transport_type: str = None

class Departure:
    """Data on Departure (Avgång) -granularity
    """
    def __init__(self):
        self.scheduled: str = None
        self.realtime: str = None
        self.delay: int = None
        self.canceled: bool = False
        self.route: Route = None
        self.trip_id: str = None

class Trip:
    """Data on Trip (basically the route)"""
    def __init__(self):
        self.trip_id

class Stop:
    """Data on Stop (Hållplats) -granularity
    """
    def __init__(self):
        self.id = None
        self.name = None
        self.lat = None
        self.lon = None
        self.departures: list[Departure] = None

def read_data(stop_id, test=False):
    """Function to connect to, and fetch API-data"""

    if test: # This is just for test-cases (so we don't make an absurd amount of API-calls)
        with open("../assets/test_data/stop_740032188_formatted.json", "r", encoding="utf-8") as file:
            payload = json.load(file)
    else:
        log("Opening API-connection")
        url = (
            "https://realtime-api.trafiklab.se/v1/departures/"
            f"{stop_id}?key={API_KEY}"
        )
        response = requests.get(url, timeout=10)
        try:
            if response.status_code != 200:
                raise RuntimeError(
                    f"API request failed:{response.status_code}"
                )
            payload = response.json()
        finally:
            response.close()
            log("Closing API-connection")
    return parse_data(payload)

def parse_data(payload):
    """Takes indata from API-call,
    then divides them up into Route[Stop[Departures]]
    """
    # transport_icons = {
    #     "BUS": "S:/assets/bus.png",
    #     "BOAT": "S:/assets/boat.png",
    #     "TRAIN": "S:/assets/train.png"
    # }
    query_time = payload["timestamp"]
    stops_by_id = {}
    if not payload["stops"]:
        return None
    for item in payload["stops"]:
        stop = Stop()
        stop.id = item["id"]
        stop.name = item["name"]
        stop.lat = item["lat"]
        stop.lon = item["lon"]
        stop.departures = []
        stops_by_id[stop.id] = stop

    for item in payload["departures"]:
        route_data = item["route"]

        route = Route()
        route.designation = route_data["designation"]
        route.direction = route_data["direction"]
        route.origin = route_data["origin"]["name"]
        route.destination = route_data["destination"]["name"]
        route.transport_type = route_data["transport_mode"]

        departure = Departure()
        departure.scheduled = item["scheduled"]
        departure.realtime = item["realtime"]
        departure.delay = item["delay"]
        departure.canceled = item["canceled"]
        departure.route = route
        departure.trip_id = item["trip"]["trip_id"]

        stop_id = item["stop"]["id"]
        stops_by_id[stop_id].departures.append(departure)

    combined_stop = Stop()
    combined_stop.id = payload["query"]["query"]
    combined_stop.name = payload["stops"][0]["name"]
    combined_stop.lat = payload["stops"][0]["lat"]
    combined_stop.lon = payload["stops"][0]["lon"]
    combined_stop.departures = [
        departure
        for child_stop in stops_by_id.values()
        for departure in child_stop.departures
    ]
    combined_stop.departures.sort(
        key = lambda departure: departure.realtime or departure.scheduled
    )

    return combined_stop, query_time

def find_journey(stops, start_stop, end_stop):
    """Finds best route between Stop A and Stop B"""
    stop_a = next((stop for stop in stops if stop.name == start_stop), None)
    stop_b = next((stop for stop in stops if stop.name == end_stop), None)
    if stop_a is None or stop_b is None:
        return None

    ### On the same route:
    for departure_a in stop_a.departures: # Loop through all departures from stop A
        for departure_b in stop_b.departures: # Loop through all departures from stop B
            if departure_a.canceled or departure_b.canceled: # If either is cancelled
                continue
            if departure_a.trip_id == departure_b.trip_id: # If there's a trip_id that matches
                time_a = departure_a.realtime or departure_a.scheduled
                time_b = departure_b.realtime or departure_b.scheduled
                trip_length = (int(time_b[11:13])*3600 # Hour
                +int(time_b[14:16])*60 # Minute
                +int(time_b[17:19]))-( # Second
                int(time_a[11:13])*3600 # Hour
                +int(time_a[14:16])*60 # Minute
                +int(time_a[17:19])) # Second
                return f"""Take route {departure_a.route.designation} towards {departure_a.route.destination} leaving at {time_a[11:19]}. Arrive by {time_b[11:19]}, the trip takes {trip_length} seconds."""

    return None

def main():
    """Main..."""
    stop1, _ = read_data("740032188")
    stop2, _ = read_data("740037242")
    stops = [stop1, stop2]
    print(find_journey(stops, "Campus Gräsvik", "Lokstallarna"))

if __name__ == "__main__":
    main()
