"""Fetch each account once and share its data across all vehicle entities."""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError
from .archive import ResponseArchive
from .const import BRANDS, DEFAULT_OPTIONS, ENDPOINTS, ENDPOINT_NAMES, TRIP_ENDPOINTS
from .data import Rejections, identifier, location, readings, reported_age, trip_readings, vehicle_id
from .trips import TripTracker

LOGGER = logging.getLogger(__name__)

# Fields of Get Vehicles that already have named attributes or the sensor state.
NAMED_VEHICLE_FIELDS = ("vin", "nickname", "name", "sellname", "type")
# Returned by _fetch when an endpoint was not queried or failed; its diagnostic sensor says why.
SKIPPED = object()


class PleosCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.client = client
        self.brand = entry.data["brand"]
        self.options = DEFAULT_OPTIONS | dict(entry.options)
        super().__init__(hass, LOGGER, config_entry=entry, name=BRANDS[self.brand],
                         update_interval=timedelta(minutes=self.options["poll_minutes"]))
        self.trips = TripTracker(hass, entry.entry_id, self.options["trip_poll_minutes"])
        self.archive = ResponseArchive(hass, entry.entry_id, self.brand) if self.options["archive"] else None

    async def _async_update_data(self):
        try:
            vehicles = await self.client.vehicles()
            if self.options["trip_events"]:
                await self.trips.load()
            result = {"status": "connected" if vehicles else "no_vehicles", "cars": {}}
            pending = []
            now = datetime.now(timezone.utc)
            if self.archive:
                await self.archive.load()
                self.archive.begin()
                self.archive.add_vehicles(now, vehicles, self.client.response_meta.get("/v1/vehicles/consent", {}))
            for vehicle in vehicles:
                car_id = vehicle_id(self.brand, vehicle["vin"])
                result["cars"][car_id] = await self._update_car(car_id, vehicle, result, pending, now)
            if self.options["trip_events"]:
                # Announce only after every car was read, so a failed poll cannot mark trips as seen.
                await self.trips.announce(self.brand, pending)
            if self.archive:
                await self.archive.flush()
            return result
        except AuthError:
            raise ConfigEntryAuthFailed("Generate a new Pleos personal API key and replace both credentials") from None
        except ApiError as error:
            raise UpdateFailed(str(error)) from None

    async def _update_car(self, car_id, vehicle, result, pending, now):
        car = {"vehicle": vehicle, "readings": {"vehicle_information": self._vehicle_information(vehicle)},
               "sources": {}, "location": None}
        fetch_trips = self.trips.due(car_id, now)
        for endpoint in ENDPOINTS:
            source = self._diagnostic_source(endpoint, now)
            car["readings"][identifier(endpoint) + "_api"] = source
            if endpoint in TRIP_ENDPOINTS and not fetch_trips:
                self.trips.reuse(car_id, endpoint, car)
                continue
            data = await self._fetch(vehicle, endpoint, source, result, now)
            if data is SKIPPED:
                continue
            if self.archive:
                self.archive.add_response(car_id, endpoint, now, source["attributes"].get("query"),
                                          source["attributes"].get("api_metadata"), data)
            if endpoint in TRIP_ENDPOINTS:
                self._apply_trips(car_id, car, endpoint, data, source, pending)
            else:
                self._apply_snapshot(car, endpoint, data, source)
        if fetch_trips and result["status"] != "rate_limited":
            self.trips.remember(car_id, now, car)
        return car

    def _vehicle_information(self, vehicle):
        attributes = {"vin": vehicle["vin"], "nickname": vehicle.get("nickname"),
                      "model_code": vehicle.get("name"), "model": vehicle.get("sellname"),
                      "api_metadata": self.client.response_meta.get("/v1/vehicles/consent", {})}
        # Keep every other field Get Vehicles returns, without overwriting the named ones above.
        for field, value in vehicle.items():
            if field not in NAMED_VEHICLE_FIELDS and value is not None:
                attributes.setdefault(identifier(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(field))), value)
        return {"name": "Vehicle information", "value": vehicle.get("type") or "UNKNOWN", "domain": "sensor",
                "entity_category": "diagnostic", "source": "vehicles", "attributes": attributes}

    @staticmethod
    def _diagnostic_source(endpoint, now):
        return {"name": ENDPOINT_NAMES[endpoint] + " API", "value": "no_data", "domain": "sensor",
                "entity_category": "diagnostic", "source": endpoint, "device_class": "enum",
                "options": ["available", "no_data", "error", "disabled"],
                "attributes": {"fetched_at": now.isoformat()}}

    async def _fetch(self, vehicle, endpoint, source, result, now):
        """Query one endpoint, recording the outcome on its diagnostic sensor."""
        if endpoint == "locations" and not self.options["location"]:
            source["value"] = "disabled"
            return SKIPPED
        if result["status"] == "rate_limited":
            source["value"] = "error"
            source["attributes"] = {"http_status": 429, "error_code": "rate_limited"}
            return SKIPPED
        path = f"/v1/vehicles/{quote(vehicle['vin'], safe='')}/{endpoint}"
        query = ""
        if endpoint in TRIP_ENDPOINTS:
            date_range = {"startDate": (now - timedelta(days=1)).strftime("%Y%m%d"),
                          "endDate": now.strftime("%Y%m%d"), "zoneId": "UTC"}
            query = "?" + "&".join(f"{key}={value}" for key, value in date_range.items())
            source["attributes"]["query"] = date_range
        try:
            data = await self.client.get(path + query)
        except ApiError as error:
            if error.status == 429:
                result["status"] = "rate_limited"
            source["value"] = "no_data" if error.code == "4045" else "error"
            source["attributes"].update(http_status=error.status, error_code=error.code)
            # An unsupported or failing endpoint must not hide other data.
            return SKIPPED
        source["attributes"]["api_metadata"] = self.client.response_meta.get(path, {})
        if isinstance(data, dict):
            source["attributes"]["data"] = data
        return data

    def _apply_trips(self, car_id, car, endpoint, data, source, pending):
        rejections = Rejections(endpoint)
        current, start = trip_readings(endpoint, data, rejections)
        source["attributes"] |= rejections.attributes()
        if self.options["trip_events"]:
            pending.extend((car_id, endpoint, trip) for trip in self.trips.unseen(car_id, endpoint, data))
        car["sources"][endpoint] = start
        car["readings"].update({key: value | {"source": endpoint} for key, value in current.items()})
        trips = data.get("trips") if isinstance(data, dict) else None
        source["value"] = "available" if isinstance(trips, list) and trips else "no_data"
        source["attributes"]["trip_count"] = len(trips) if isinstance(trips, list) else 0

    def _apply_snapshot(self, car, endpoint, data, source):
        stamp = data.get("timestamp") if isinstance(data, dict) else None
        car["sources"][endpoint] = stamp
        rejections = Rejections(endpoint)
        current = readings(endpoint, data, car["vehicle"].get("type"), rejections)
        source["attributes"] |= rejections.attributes()
        car["readings"].update({key: value | {"source": endpoint} for key, value in current.items()})
        source["value"] = "available" if current else "no_data"
        if endpoint == "locations":
            car["location"] = location(data)
        age = reported_age(stamp)
        if age is None:
            return
        prefix = identifier(endpoint)
        for suffix, name, reading in (
            ("reported_at", " last reported", {"value": stamp, "device_class": "timestamp"}),
            ("data_age", " data age", {"value": round(age / 60, 1), "unit_of_measurement": "min",
                                       "device_class": "duration", "state_class": "measurement"}),
        ):
            car["readings"][prefix + "_" + suffix] = reading | {
                "name": ENDPOINT_NAMES[endpoint] + name, "domain": "sensor", "source": endpoint,
                "entity_category": "diagnostic",
            }
