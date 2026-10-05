"""Module to fetch, and return data"""
from datetime import datetime
import json
import requests
from secrets import API_KEY
# from debug_log import log

class Route:
    """Data on Route (Linje) -granularity
    """
    def __init__(self):
        self.designation: str = None
        self.direction: str = None
        self.origin: str = None
        self.destination: str = None
        self.stops: list = None

class Departure:
    """Data on Departure (Avgång) -granularity
    """
    def __init__(self):
        self.scheduled: datetime = None
        self.realtime: datetime = None
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

def read_data(test=False):
    """Function to connect to, and fetch API-data"""

    if test == True:
        with open("test_data/stop_740032188_formatted.json", "r", encoding="utf-8") as file:
            payload = json.load(file)
        return parse_data(payload)
    else:
        REQUESTED_STOP = "740032188" # Campus Gräsvik
        response = requests.get(f"https://realtime-api.trafiklab.se/v1/departures/{REQUESTED_STOP}?key={API_KEY}", timeout=10)
        try:
            if response.status_code != 200:
                print(f"api request failed({response.status_code})")
                raise RuntimeError(
                    f"API request failed:{response.status_code}"
                )
            payload = response.json()
            print("API-data fetched successfully")
            return parse_data(payload)
        finally:
            response.close()


def parse_data(payload):
    """Takes indata from API-call,
    then divides them up into Route[Stop[Departures]]
    """
    stops_by_id = {}
    print(f"Payload_size:{len(payload)}")
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

        stop_id = item["stop"]["id"]
        stops_by_id[stop_id].departures.append(departure)
    return list(stops_by_id.values())

def main():
    """Main..."""
    data = read_data()
    print(json.dumps(data, default=vars, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    main()
