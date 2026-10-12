"""Fetch each account once and share its data across all vehicle entities."""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError
from .const import BRANDS, DEFAULT_OPTIONS, ENDPOINTS, ENDPOINT_NAMES, TRIP_ENDPOINTS
from .data import identifier, location, readings, reported_age, trip_readings, vehicle_id

LOGGER = logging.getLogger(__name__)


class PleosCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.client = client
        self.brand = entry.data["brand"]
        self.options = DEFAULT_OPTIONS | dict(entry.options)
        super().__init__(hass, LOGGER, config_entry=entry, name=BRANDS[self.brand],
                         update_interval=timedelta(minutes=self.options["poll_minutes"]))

    async def _async_update_data(self):
        try:
            vehicles = await self.client.vehicles()
            result = {"status": "connected" if vehicles else "no_vehicles", "cars": {}}
            now = datetime.now(timezone.utc)
            date_range = {"startDate": (now - timedelta(days=1)).strftime("%Y%m%d"),
                          "endDate": now.strftime("%Y%m%d"), "zoneId": "UTC"}
            for vehicle in vehicles:
                car = {"vehicle": vehicle, "readings": {}, "sources": {}, "location": None}
                result["cars"][vehicle_id(self.brand, vehicle["vin"])] = car
                car["readings"]["vehicle_information"] = {
                    "name": "Vehicle information", "value": vehicle.get("type") or "UNKNOWN", "domain": "sensor",
                    "entity_category": "diagnostic", "source": "vehicles",
                    "attributes": {"vin": vehicle["vin"], "nickname": vehicle.get("nickname"),
                                   "model_code": vehicle.get("name"), "model": vehicle.get("sellname"),
                                   "api_metadata": self.client.response_meta.get("/v1/vehicles/consent", {})},
                }
                for endpoint in ENDPOINTS:
                    prefix = identifier(endpoint)
                    source = {"name": ENDPOINT_NAMES[endpoint] + " API", "value": "no_data", "domain": "sensor",
                              "entity_category": "diagnostic", "source": endpoint, "device_class": "enum",
                              "options": ["available", "no_data", "error", "disabled"],
                              "attributes": {"fetched_at": now.isoformat()}}
                    car["readings"][prefix + "_api"] = source
                    if endpoint == "locations" and not self.options["location"]:
                        source["value"] = "disabled"
                        continue
                    path = f"/v1/vehicles/{quote(vehicle['vin'], safe='')}/{endpoint}"
                    query = "?" + "&".join(f"{key}={value}" for key, value in date_range.items()) if endpoint in TRIP_ENDPOINTS else ""
                    if query:
                        source["attributes"]["query"] = date_range
                    try:
                        data = await self.client.get(path + query)
                    except ApiError as error:
                        if error.status in (0, 429):
                            raise
                        source["value"] = "no_data" if error.code in ("4045", "5006", "403", "4101") else "error"
                        source["attributes"].update(http_status=error.status, error_code=error.code)
                        # An unsupported or failing endpoint must not hide other data.
                        continue
                    source["attributes"]["api_metadata"] = self.client.response_meta.get(path, {})
                    if isinstance(data, dict):
                        source["attributes"]["data"] = data
                    stamp = data.get("timestamp") if isinstance(data, dict) else None
                    if endpoint in TRIP_ENDPOINTS:
                        current, start = trip_readings(endpoint, data)
                        car["sources"][endpoint] = start
                        car["readings"].update({key: value | {"source": endpoint} for key, value in current.items()})
                        trips = data.get("trips") if isinstance(data, dict) else None
                        source["value"] = "available" if isinstance(trips, list) and trips else "no_data"
                        source["attributes"]["trip_count"] = len(trips) if isinstance(trips, list) else 0
                        continue
                    age = reported_age(stamp)
                    car["sources"][endpoint] = stamp
                    current = readings(endpoint, data, vehicle.get("type"))
                    car["readings"].update({key: value | {"source": endpoint} for key, value in current.items()})
                    source["value"] = "available" if current else "no_data"
                    if endpoint == "locations":
                        car["location"] = location(data)
                    if age is not None:
                        for suffix, reading in (
                            ("reported_at", {"value": stamp, "device_class": "timestamp"}),
                            ("data_age", {"value": round(age / 60, 1), "unit_of_measurement": "min", "device_class": "duration", "state_class": "measurement"}),
                        ):
                            car["readings"][prefix + "_" + suffix] = reading | {
                                "name": ENDPOINT_NAMES[endpoint] + (" last reported" if suffix == "reported_at" else " data age"),
                                "domain": "sensor", "source": endpoint,
                                "entity_category": "diagnostic",
                            }
            return result
        except AuthError:
            raise ConfigEntryAuthFailed("Generate a new Pleos personal API key and replace both credentials") from None
        except ApiError as error:
            raise UpdateFailed(str(error)) from None
