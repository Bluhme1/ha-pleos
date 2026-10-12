"""Integration constants."""

DOMAIN = "pleos_vehicle_data"
BRANDS = {"hyundai": "Hyundai", "kia": "Kia", "genesis": "Genesis"}
SNAPSHOT_ENDPOINTS = ("batteries", "powertrains", "driving", "status", "locations", "freezer")
TRIP_ENDPOINTS = ("powertrains/data", "speed", "driving/data", "status/data")
ENDPOINTS = SNAPSHOT_ENDPOINTS + TRIP_ENDPOINTS
ENDPOINT_NAMES = {
    "batteries": "Battery charging", "powertrains": "Powertrain status", "driving": "Driving status",
    "status": "Vehicle status", "locations": "Location", "freezer": "Freezer status",
    "powertrains/data": "Powertrain trips", "speed": "Speed trips",
    "driving/data": "Driving trips", "status/data": "Vehicle status trips",
}
DEFAULT_OPTIONS = {"poll_minutes": 15, "stale_minutes": 60, "location": True}
