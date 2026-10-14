"""Every new trip gets its own entity state, so Home Assistant records and exports each one."""

import logging
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.core import EVENT_STATE_CHANGED, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.pleos_vehicle_data.const import DOMAIN
from custom_components.pleos_vehicle_data.coordinator import PleosCoordinator
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

    async def test_each_new_trip_is_shown_in_order(self):
        first = trip(300, 10)
        self.serve(speed=[first])
        await self.start()
        trips = [trip(200, 20), trip(100, 30), trip(10, 40)]
        self.serve(speed=[first, *trips])
        await self.poll()
        self.assertEqual(self.shown("speed"), [(str(t["location"]["speed"][0]), t["triggerStartTime"]) for t in trips])

        # Nothing new: nothing is shown again.
        await self.poll()
        self.assertEqual(len(self.shown("speed")), 3)

    async def test_endpoints_step_together_by_trip_start(self):
        # The same drive has the same start on every trip endpoint.
        night, morning, evening = stamp(900), stamp(600), stamp(60)
        self.serve(speed=[trip(night, 5)], driving=[drive(night, 100, 101)])
        await self.start()
        self.serve(speed=[trip(night, 5), trip(morning, 50), trip(evening, 70)],
                   driving=[drive(night, 100, 101), drive(morning, 101, 111)])
        await self.poll()
        speeds = [value for value, _ in self.shown("speed")]
        distances = [value for value, _ in self.shown("trip_distance")]
        self.assertEqual(speeds, ["50", "70"])
        # The driving endpoint has no evening trip, so its morning trip stays shown: one change only.
        self.assertEqual(distances, ["10"])

    async def test_a_late_older_trip_is_shown_then_the_latest_again(self):
        latest = trip(30, 80)
        self.serve(speed=[latest])
        await self.start()
        late = trip(120, 60)
        self.serve(speed=[late, latest])
        await self.poll()
        self.assertEqual([value for value, _ in self.shown("speed")], ["60", "80"])

    async def test_restart_does_not_show_trips_again(self):
        self.serve(speed=[trip(300, 10), trip(100, 20)])
        await self.start()
        restarted = PleosCoordinator(self.hass, self.entry, self.client)
        self.addAsyncCleanup(restarted.async_shutdown)
        await self.start(restarted)
        self.changes.clear()
        await self.poll(restarted)
        self.assertEqual(self.shown("speed"), [])

    async def test_first_refresh_marks_trips_without_replaying(self):
        self.serve(speed=[trip(300, 10), trip(200, 20), trip(100, 30)])
        await self.start()
        self.assertEqual(len(self.coordinator.trips.published[CAR_ID]["speed"]), 3)
        await self.poll()
        self.assertEqual(self.shown("speed"), [])
