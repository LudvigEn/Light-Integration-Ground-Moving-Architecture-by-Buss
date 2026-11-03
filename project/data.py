"""Module to fetch, and return data"""
import json
from secrets import API_KEY # pylint:disable=no-name-in-module
import requests
try:
    from debug_log import log
except ImportError:
    def log(message):
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

class Departure:
    """Data on Departure (Avgång) -granularity
    """
    def __init__(self):
        self.scheduled: str = None
        self.realtime: str = None
        self.delay: int = None
        self.canceled: bool = False
        self.route: Route = None

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
        with open("test_data/stop_740032188_formatted.json", "r", encoding="utf-8") as file:
            payload = json.load(file)
    else:
        log("Opening API-connection")
        response = requests.get(f"https://realtime-api.trafiklab.se/v1/departures/{stop_id}?key={API_KEY}", timeout=10)
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
    stops_by_id = {}
    # print(f"Payload_size:{len(payload)}")
    if payload["stops"] == "":
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

        departure = Departure()
        departure.scheduled = item["scheduled"]
        departure.realtime = item["realtime"]
        departure.delay = item["delay"]
        departure.canceled = item["canceled"]
        departure.route = route

        stop.departures.append(departure)

    return stop

def main():
    """Main..."""
    data = read_data("740032188")
    print(json.dumps(data, default=vars, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    main()
