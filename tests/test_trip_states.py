"""Trip sensors show the latest reading without replaying historical states."""

import logging
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.core import EVENT_STATE_CHANGED, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.pleos_vehicle_data.const import DOMAIN
from custom_components.pleos_vehicle_data.data import vehicle_id
from custom_components.pleos_vehicle_data.sensor import ReadingSensor

from support import CAR, HomeAssistantTestCase, stamp

CAR_ID = vehicle_id("kia", CAR["vin"])


def trip(start, speed):
    start = stamp(start) if isinstance(start, int) else start
    return {"triggerStartTime": start, "tripLength": 60000, "location": {"speed": [speed], "speedUnit": ["kph"]}}


def drive(start, start_km, end_km):
    start = stamp(start) if isinstance(start, int) else start
    return {"triggerStartTime": start, "tripLength": 60000, "odometer": {"value": [start_km, end_km]}}


class TripStateTests(HomeAssistantTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await entity_registry.async_load(self.hass, load_empty=True)
        self.changes = []

        @callback
        def record(event):
            if event.data["new_state"] is not None:
                self.changes.append(event.data["new_state"])
        self.addCleanup(self.hass.bus.async_listen(EVENT_STATE_CHANGED, record))

    def serve(self, speed=(), driving=()):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        payloads = {"/speed?": {"trips": list(speed)}, "/driving/data?": {"trips": list(driving)}}
        self.client.get = AsyncMock(side_effect=lambda path: next(
            (payload for marker, payload in payloads.items() if marker in path), None))

    async def start(self, coordinator=None):
        """Poll once and add the trip entities, as Home Assistant does at setup."""
        coordinator = coordinator or self.coordinator
        if getattr(self, "platform", None):
            await self.platform.async_reset()  # A restart replaces the entities.
        coordinator.data = await coordinator._async_update_data()
        coordinator.last_update_success = True
        platform = EntityPlatform(hass=self.hass, logger=logging.getLogger(__name__), domain="sensor",
                                  platform_name=DOMAIN, platform=None, scan_interval=timedelta(minutes=15),
                                  entity_namespace=None)
        platform.config_entry = self.entry
        readings = coordinator.data["cars"][CAR_ID]["readings"]
        await platform.async_add_entities([ReadingSensor(coordinator, CAR_ID, key, readings[key])
                                           for key in ("speed_location_speed", "driving_data_trip_distance")
                                           if key in readings])
        self.platform = platform
        self.addAsyncCleanup(platform.async_reset)
        self.changes.clear()

    async def poll(self, coordinator=None):
        coordinator = coordinator or self.coordinator
        coordinator.trips.cache.clear()
        await coordinator.async_refresh()
        await self.hass.async_block_till_done()

    def shown(self, name):
        return [(state.state, state.attributes.get("trip_start")) for state in self.changes
                if state.entity_id.endswith(f"_{name}_last_trip")]

    async def test_batch_and_late_trips_do_not_replay_old_sensor_states(self):
        first = trip(300, 10)
        self.serve(speed=[first])
        await self.start()
        latest = trip(10, 40)
        self.serve(speed=[first, trip(200, 20), trip(100, 30), latest])
        await self.poll()
        self.assertEqual(self.shown("speed"), [("40", latest["triggerStartTime"])])
        self.changes.clear()
        self.serve(speed=[trip(150, 25), latest])
        await self.poll()
        self.assertEqual(self.shown("speed"), [])
