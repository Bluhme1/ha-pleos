"""Fetch each account once and share its data across all vehicle entities."""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError
from .const import (BRANDS, DEFAULT_OPTIONS, DOMAIN, ENDPOINTS, ENDPOINT_NAMES, TRIP_ENDPOINTS, TRIP_EVENT,
                    TRIP_MEMORY_DAYS)
from .data import (identifier, location, new_trips, prune_seen, readings, reported_age, trip_readings,
                   vehicle_id)

LOGGER = logging.getLogger(__name__)


class PleosCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.client = client
        self.brand = entry.data["brand"]
        self.options = DEFAULT_OPTIONS | dict(entry.options)
        super().__init__(hass, LOGGER, config_entry=entry, name=BRANDS[self.brand],
                         update_interval=timedelta(minutes=self.options["poll_minutes"]))
        # Trip start times already announced, per car and endpoint, kept across restarts.
        self.trip_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.trips")
        self.seen_trips = None
        # Last trip results per car, reused between trip fetches.
        self.trip_cache = {}

    async def _load_seen_trips(self):
        if self.seen_trips is None:
            stored = await self.trip_store.async_load()
            self.seen_trips = stored if isinstance(stored, dict) else {}
        return self.seen_trips

    async def _announce_trips(self, pending):
        """Fire one event per new trip, oldest first, then remember them."""
        seen = await self._load_seen_trips()
        devices = dr.async_get(self.hass) if pending else None
        for car_id, endpoint, trip in pending:
            device = devices.async_get_device_by_identifier((DOMAIN, car_id), self.config_entry.entry_id)
            self.hass.bus.async_fire(TRIP_EVENT, {
                "vehicle_id": car_id, "device_id": device.id if device else None, "brand": self.brand,
                "endpoint": endpoint, "trip_start": trip["triggerStartTime"],
                "trip_length_ms": trip.get("tripLength"), "trip": trip,
            })
            seen.setdefault(car_id, {}).setdefault(endpoint, []).append(trip["triggerStartTime"])
        max_age = TRIP_MEMORY_DAYS * 86400
        pruned = {car_id: {endpoint: kept for endpoint, starts in endpoints.items()
                           if (kept := prune_seen(starts, max_age))}
                  for car_id, endpoints in seen.items()}
        pruned = {car_id: endpoints for car_id, endpoints in pruned.items() if endpoints}
        if pending or pruned != seen:
            self.seen_trips = pruned
            await self.trip_store.async_save(pruned)

    async def _async_update_data(self):
        try:
            vehicles = await self.client.vehicles()
            seen = await self._load_seen_trips() if self.options["trip_events"] else {}
            pending = []
            result = {"status": "connected" if vehicles else "no_vehicles", "cars": {}}
            now = datetime.now(timezone.utc)
            date_range = {"startDate": (now - timedelta(days=1)).strftime("%Y%m%d"),
                          "endDate": now.strftime("%Y%m%d"), "zoneId": "UTC"}
            for vehicle in vehicles:
                car = {"vehicle": vehicle, "readings": {}, "sources": {}, "location": None}
                car_id = vehicle_id(self.brand, vehicle["vin"])
                result["cars"][car_id] = car
                cached = self.trip_cache.get(car_id)
                # Trip data arrives with hours of delay, so trips are fetched less often than snapshots.
                fetch_trips = cached is None or now - cached["fetched_at"] >= timedelta(
                    minutes=self.options["trip_poll_minutes"])
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
                    if endpoint in TRIP_ENDPOINTS and not fetch_trips:
                        if reused := cached["endpoints"].get(endpoint):
                            car["readings"].update(reused["readings"])
                            car["sources"][endpoint] = reused["start"]
                        continue
                    if endpoint == "locations" and not self.options["location"]:
                        source["value"] = "disabled"
                        continue
                    if result["status"] == "rate_limited":
                        source["value"] = "error"
                        source["attributes"] = {"http_status": 429, "error_code": "rate_limited"}
                        continue
                    path = f"/v1/vehicles/{quote(vehicle['vin'], safe='')}/{endpoint}"
                    query = "?" + "&".join(f"{key}={value}" for key, value in date_range.items()) if endpoint in TRIP_ENDPOINTS else ""
                    if query:
                        source["attributes"]["query"] = date_range
                    try:
                        data = await self.client.get(path + query)
                    except ApiError as error:
                        if error.status == 429:
                            result["status"] = "rate_limited"
                        source["value"] = "no_data" if error.code == "4045" else "error"
                        source["attributes"].update(http_status=error.status, error_code=error.code)
                        # An unsupported or failing endpoint must not hide other data.
                        continue
                    source["attributes"]["api_metadata"] = self.client.response_meta.get(path, {})
                    if isinstance(data, dict):
                        source["attributes"]["data"] = data
                    stamp = data.get("timestamp") if isinstance(data, dict) else None
                    if endpoint in TRIP_ENDPOINTS:
                        current, start = trip_readings(endpoint, data)
                        if self.options["trip_events"]:
                            known = set(seen.get(car_id, {}).get(endpoint, ()))
                            pending.extend((car_id, endpoint, trip) for trip in new_trips(data, known))
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
                if fetch_trips and result["status"] != "rate_limited":
                    self.trip_cache[car_id] = {"fetched_at": now, "endpoints": {
                        endpoint: {"start": car["sources"].get(endpoint),
                                   "readings": {key: reading for key, reading in car["readings"].items()
                                                if reading.get("source") == endpoint}}
                        for endpoint in TRIP_ENDPOINTS}}
            if self.options["trip_events"]:
                # Announce only after every car was read, so a failed poll cannot mark trips as seen.
                await self._announce_trips(pending)
            return result
        except AuthError:
            raise ConfigEntryAuthFailed("Generate a new Pleos personal API key and replace both credentials") from None
        except ApiError as error:
            raise UpdateFailed(str(error)) from None
