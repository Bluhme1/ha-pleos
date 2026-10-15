"""Last valid range readings, including their original reporting time."""

import logging

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .data import finite_number, reported_age

LOGGER = logging.getLogger(__name__)
RANGE_PREFIX = "powertrains_distancetoempties_"


def range_store(hass, entry_id):
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.ranges")


class RangeCache:
    def __init__(self, hass, entry_id):
        self.store = range_store(hass, entry_id)
        self.values = None
        self.dirty = False

    async def apply(self, cars):
        if self.values is None:
            try:
                stored = await self.store.async_load()
            except (HomeAssistantError, OSError):
                LOGGER.warning("Could not load saved ranges; keeping new ranges only in memory until reload")
                # A failed read must not overwrite a cache we could not inspect.
                self.store.make_read_only()
                stored = None
            self.values = {}
            for car_id, entries in (stored.items() if isinstance(stored, dict) else ()):
                if not isinstance(entries, dict):
                    continue
                for key, saved in entries.items():
                    if (not isinstance(key, str) or not key.startswith(RANGE_PREFIX) or not isinstance(saved, dict)
                            or not finite_number(saved.get("value")) or not 1 <= saved["value"] <= 4095
                            or saved.get("unit") not in ("km", "mi", "m", "ft")
                            or reported_age(saved.get("reported_at")) is None
                            or not isinstance(saved.get("name"), str) or len(saved["name"]) > 255):
                        continue
                    self.values.setdefault(car_id, {})[key] = saved

        kept = {}
        for car_id, car in cars.items():
            saved = dict(self.values.get(car_id, {}))
            stamp = car["sources"].get("powertrains")
            current = {key: reading for key, reading in car["readings"].items() if key.startswith(RANGE_PREFIX)}
            if reported_age(stamp) is not None:
                for key, reading in current.items():
                    saved[key] = {"value": reading["value"], "unit": reading["unit_of_measurement"],
                                  "name": reading["name"], "reported_at": stamp}
                    reading.setdefault("attributes", {})["last_known"] = False
            else:
                current = {}
            for key, reading in saved.items():
                if key not in current:
                    car["readings"][key] = {
                        "value": reading["value"], "unit_of_measurement": reading["unit"], "name": reading["name"],
                        "domain": "sensor", "device_class": "distance", "state_class": "measurement", "source": "powertrains",
                        "attributes": {"reported_at": reading["reported_at"], "last_known": True, "data_stale": True},
                    }
            if saved:
                kept[car_id] = saved
        self.dirty |= kept != self.values
        self.values = kept
        if self.dirty:
            try:
                await self.store.async_save(kept)
            except OSError:
                LOGGER.warning("Could not save ranges; they may be lost after restart")
            else:
                self.dirty = False
