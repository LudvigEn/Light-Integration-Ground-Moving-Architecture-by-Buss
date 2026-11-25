"""Module to fetch, and return data"""
import json
from secrets import TRAFIKLAB_API_KEY, RESROBOT_API_KEY # pylint:disable=no-name-in-module
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


class Stop:
    """Data on Stop (Hållplats) -granularity
    """
    def __init__(self):
        self.id = None
        self.name = None
        self.lat = None
        self.lon = None
        self.departures: list[Departure] = None


class Leg:
    """Data on Leg(Part of journey) -granularity"""
    def __init__(self, data, names_by_id):
        origin = data["Origin"]
        destination = data["Destination"]

        self.origin = names_by_id.get(
            str(origin.get("extId", "")),
            origin["name"],
        )
        self.destination = names_by_id.get(
            str(destination.get("extId", "")),
            destination["name"],
        )
        self.departure_time = origin["time"]
        d_hours, d_minutes, d_seconds = map(int, self.departure_time.split(":"))
        self.departure_time_seconds = d_hours*3600 + d_minutes*60 + d_seconds
        self.arrival_time = destination["time"]
        a_hours, a_minutes, a_seconds = map(int, self.arrival_time.split(":"))
        self.arrival_time_seconds = a_hours*3600 + a_minutes*60 + a_seconds
        self.duration = self.arrival_time_seconds - self.departure_time_seconds
        self.line = data.get("number")
        if data["type"] == "WALK":
            self.walk = True
            self.dist = data["dist"]
        else:
            self.walk = False
        self.direction = data.get("direction") or ""
        if self.direction.endswith(" kn)"):
            self.direction = self.direction.rsplit(" (", 1)[0]

    def __repr__(self):
        return str(self)

    def __str__(self):
        if not self.walk:
            return f"\t{self.departure_time[:-3]}- Take line {self.line} towards {self.direction}, get of at {self.destination}."
        else:
            return f"\t{self.departure_time[:-3]}- Walk {self.dist}m ({round(self.dist/self.duration, 1)}m/s) to {self.destination}"

    def get_origin(self):
        """Return Origin Stop"""
        return self.origin

    def get_destination(self):
        """Return Destination Stop"""
        return self.destination

    def get_line(self):
        """Return line (i.e. route)"""
        return self.line

    def get_duration(self):
        """Return duration of leg (in seconds)"""
        return self.duration

    def get_distance(self):
        """Return duration of leg (in seconds)"""
        if self.walk is True:
            return self.dist
        else:
            return None


class Journey:
    """Data on Journey(Resa) -granularity"""
    def __init__(self, data, names_by_id):
        origin = data["Origin"]
        destination = data["Destination"]

        self.origin = names_by_id.get(
            str(origin.get("extId", "")),
            origin["name"],
        )
        self.destination = names_by_id.get(
            str(destination.get("extId", "")),
            destination["name"],
        )
        self.departure_time = origin["time"]
        d_hours, d_minutes, d_seconds = map(int, self.departure_time.split(":"))
        self.departure_time_seconds = d_hours*3600 + d_minutes*60 + d_seconds
        self.arrival_time = destination["time"]
        a_hours, a_minutes, a_seconds = map(int, self.arrival_time.split(":"))
        self.arrival_time_seconds = a_hours*3600 + a_minutes*60 + a_seconds
        self.duration  = self.arrival_time_seconds - self.departure_time_seconds

        self.legs = [
            Leg(item, names_by_id)
            for item in data["LegList"]["Leg"]
        ]

    def __str__(self):
        msg = f"{self.departure_time[:-3]} from {self.origin} to {self.destination}. "
        msg += f"Arrive by {self.arrival_time[:-3]}. "
        msg += f"Total travel time: {round(self.duration/60)} minutes."
        for leg in self.legs:
            msg += f"\n{leg}"
        return msg

    def __repr__(self):
        return str(self)

    def __int__(self):
        return self.duration

    def __lt__(self, other):
        if not isinstance(other, Journey):
            return NotImplemented

        return (
            self.arrival_time_seconds
        ) < (
            other.arrival_time_seconds
        )

    def get_departure_time(self):
        """Returns time (as a string)"""
        return self.departure_time

    def get_arrival_time(self):
        """Returns time (as a string)"""
        return self.arrival_time

    def get_origin(self):
        """Returns Journey Origin"""
        return self.origin

    def get_destination(self):
        """Returns Journey Destination"""
        return self.destination

    def get_legs(self):
        """Returns Legs (part of Journey)"""
        return self.legs


def read_data(stop_id, test=False):
    """Function to connect to, and fetch API-data"""

    if test: # This is just for test-cases (so we don't make an absurd amount of API-calls)
        with open("../assets/test_data/stop_740032188_formatted.json", "r", encoding="utf-8") as file:
            payload = json.load(file)
    else:
        log("Opening Trafiklab-API-connection")
        url = (
            "https://realtime-api.trafiklab.se/v1/departures/"
            f"{stop_id}?key={TRAFIKLAB_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        try:
            if response.status_code != 200:
                raise RuntimeError(
                    f"API request failed:{response.status_code}"
                )
            payload = response.json()
            log(f"Success, stops: {len(payload["stops"])}")
        finally:
            response.close()
            log("Closing Trafiklab-API-connection")
    return parse_data(payload)


def parse_data(payload):
    """Takes indata from API-call,
    then divides them up into Route[Stop[Departures]]
    """
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


def find_journey(stop_a, stop_b, transport_type="ALL"):
    """Uses ResRobot API to find Journeys between stop_a and stop_b"""

    #### FETCH STOP IDS
    module_dir = __file__.replace("\\", "/").rpartition("/")[0] or "."
    with open(module_dir + "/STOPS.json", "r", encoding="utf-8") as file:
        STOPS = json.load(file)
    start_stop = STOPS[transport_type][stop_a]
    end_stop = STOPS[transport_type][stop_b]
    # ResRobots stop-names are weirdly formatted and needs
    names_by_id = {
        str(stop_id): name
        for name, stop_id in STOPS["ALL"].items()
    }

    #### FETCH API DATA FOR STOP IDS
    log("Opening ResRobot-API-connection")
    url = (
        "https://api.resrobot.se/v2.1/trip?format=json&originId="
        f"{start_stop}"
        f"&destId={end_stop}"
        f"&passlist=true&showPassingPoints=true&accessId={RESROBOT_API_KEY}"
    )
    response = requests.get(url, timeout=10)
    try:
        if response.status_code != 200:
            raise RuntimeError(
                f"API request failed:{response.status_code}"
            )
        payload = response.json()
        log(f"Success, trips: {len(payload["Trip"])}")
    finally:
        response.close()
        log("Closing ResRobot-API-connection")

    ### PROCESS DATA
    journeys = [Journey(item, names_by_id) for item in payload["Trip"]]
    journeys.sort()
    return journeys, payload  # Payload is only interesting for manual runs


def main():
    """Main..."""
    journeys, payload = find_journey("Campus Gräsvik", "Jämjö centrum")
    with open("./assets/test_data/route_planner_output.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)
    for journey in journeys:
        print(journey)

if __name__ == "__main__":
    main()
