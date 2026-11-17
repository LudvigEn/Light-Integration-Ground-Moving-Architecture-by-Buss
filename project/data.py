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

    def __str__(self):
        return f"{self.designation}:an towards {self.direction}"

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

class Stop:
    """Data on Stop (Hållplats) -granularity
    """
    def __init__(self):
        self.id = None
        self.name = None
        self.lat = None
        self.lon = None
        self.departures: list[Departure] = None

    def __str__(self):
        return self.name

def read_data(stop_id, test=False, dep="dep"):
    """Function to connect to, and fetch API-data"""

    if test: # This is just for test-cases (so we don't make an absurd amount of API-calls)
        with open("../assets/test_data/stop_740032188_formatted.json", "r", encoding="utf-8") as file:
            payload = json.load(file)
    else:
        # log("Opening API-connection")
        if dep == "arr":
            dep_or_arr = "arrivals/"
        else:
            dep_or_arr = "departures/"
        url = (
            "https://realtime-api.trafiklab.se/v1/"
            f"{dep_or_arr}{stop_id}?key={API_KEY}"
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
            # log("Closing API-connection")
    return parse_data(payload)

def parse_data(payload):
    """Takes indata from API-call,
    then divides them up into Route[Stop[Departures]]
    """
    query_time = payload["timestamp"]
    stops_by_id = {}
    if "arrivals" in payload:
        payload["departures"] = payload["arrivals"]
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
    stop_a = next((stop for stop in stops if stop.name == start_stop), None) # Start-stop
    stop_b = next((stop for stop in stops if stop.name == end_stop), None) # End-stop

    def extract_trip_id(stop):
        """This extracts all trips 'touching' a stop."""
        try:
            return {
                departure.trip_id
                for departure in stop.departures
                if departure.trip_id is not None and not departure.canceled
            }
        except AttributeError:
            return None


    def one_leg(start_stop, end_stop):
        """Trip between start_stop and end_stop"""
        if start_stop is None or end_stop is None: # If input is faulty
            return None
        for departure_a in start_stop.departures: # Loop through all departures from stop A
            for departure_b in end_stop.departures: # Loop through all departures from stop B
                time_a = departure_a.realtime or departure_a.scheduled # Realtime if exists, otherwise scheduled
                time_b = departure_b.realtime or departure_b.scheduled # Realtime if exists, otherwise scheduled
                time_b_seconds = (int(time_b[11:13])*3600 # Hour
                + int(time_b[14:16])*60 # Minute
                + int(time_b[17:19])) # Seconds
                time_a_seconds = (int(time_a[11:13])*3600 # Hour
                + int(time_a[14:16])*60 # Minute
                + int(time_a[17:19])) # Second
                if time_b_seconds <= time_a_seconds: # No "backwards" trips
                    continue
                if departure_a.canceled or departure_b.canceled: # If either is cancelled
                    continue
                if departure_a.trip_id == departure_b.trip_id: # If there's a trip_id that matches

                    trip_length = time_b_seconds - time_a_seconds # Total duration of this leg
                    return_string =  f"""Take route {departure_a.route.designation}({departure_a.route.transport_type}) towards {departure_a.route.destination} leaving at {time_a[11:19]}. Arrive by {time_b[11:19]}, the trip takes {trip_length} seconds"""
                    return time_a_seconds, time_b_seconds, return_string
        return None


    journeys = []
    ### No Transfer:
    if one_leg(stop_a, stop_b) is not None: # If there is a valid trip between Stop A and B
        journeys.append(one_leg(stop_a, stop_b)[2])
    else:
        log(f"No one-leg-journey between {stop_a} and {stop_b}")

    #########################################################################################
    ### Here comes the hard part, we need to check all stops for possible transfer-stops: ###
    #########################################################################################
    module_dir = __file__.replace("\\", "/").rpartition("/")[0] or "."
    with open(module_dir + "/STOPS.json", "r", encoding="utf-8") as file:
        all_stops = json.load(file)
    stop_list = []
    for stop_id in all_stops["ALL"].values():
        result = read_data(stop_id)
        if result is not None:
            stop, query_time = result
            stop_list.append(stop)
    # Now we have data on all stops.

    trips_a = extract_trip_id(stop_a)
    trips_b = extract_trip_id(stop_b)
    transfer_stops = []
    for stop in stop_list:
        if stop.id in (stop_a.id, stop_b.id):
            continue
        trips_here = extract_trip_id(stop)
        if trips_here & trips_a and trips_here & trips_b:
            transfer_stops.append(stop)
    candidate_transfer_stops = "Candidate transfer stops:",[stop.name for stop in transfer_stops]
    log(candidate_transfer_stops)
    for transfer_stop in transfer_stops:
        # print("Transfer stop:", transfer_stop)
        first_leg = one_leg(stop_a, transfer_stop) # From Stop A to Transfer-stop
        second_leg = one_leg(transfer_stop, stop_b) # From Transfer-stop to Stop B
        # print("First leg", first_leg)
        # print("Second leg", second_leg)

        if first_leg is None or second_leg is None: # If legs are unstable (e.g. arrive before leave)
            continue
        first_start, first_end, first_string = first_leg # Split up output into depart-time, arrival-time and string
        second_start, second_end, second_string = second_leg # Split up output into depart-time, arrival-time and string
        if first_end <= second_start: # As long as arrival-time of first-leg is less than departure-time of second-leg.
            # print("Connection possible:", first_end <= second_start)
            total_travel_time = second_end - first_start
            journeys.append((first_string + ", and then " + second_string + f". Total trip time:{total_travel_time} seconds.", total_travel_time))
    journeys.sort(
        key=lambda journey: journey[1]
    )
    if journeys:
        for journey in journeys:
            print(journey[0])
    else:
        return None

def main():
    """Main..."""
    stop1, _ = read_data("740032188")
    stop2, _ = read_data("740001537", False, "arr")
    stops = [stop1, stop2]
    for stop in stops:
        print(stop, stop.id)
    print(find_journey(stops, "Campus Gräsvik", "Bergåsa station"))

if __name__ == "__main__":
    main()
