"""Trip events and the trip polling interval."""

import unittest
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry

from custom_components.pleos_vehicle_data import async_remove_entry
from custom_components.pleos_vehicle_data.api import ApiError, AuthError
from custom_components.pleos_vehicle_data.const import DOMAIN
from custom_components.pleos_vehicle_data.coordinator import PleosCoordinator
from custom_components.pleos_vehicle_data.data import vehicle_id

from support import CAR, HomeAssistantTestCase, stamp


class TripPollingTests(HomeAssistantTestCase):
    async def test_new_trips_fire_one_event_each_across_polls_and_restarts(self):
        events = self.capture_trip_events()
        first = {"triggerStartTime": stamp(240), "tripLength": 2000,
                 "location": {"speed": [10, 20], "speedUnit": ["kph", "kph"]}}
        second = {"triggerStartTime": stamp(120), "tripLength": 1000, "wheel": {"speedFrontLeft": [5]}}
        self.serve_trips(second, first)
        await self.coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual([event.data["trip_start"] for event in events], [first["triggerStartTime"], second["triggerStartTime"]])
        self.assertEqual(events[0].data["trip"], first)
        self.assertEqual(events[0].data["trip_length_ms"], 2000)
        self.assertEqual(events[0].data["endpoint"], "speed")
        self.assertEqual(events[0].data["vehicle_id"], vehicle_id("kia", CAR["vin"]))
        self.assertEqual(events[0].data["brand"], "kia")
        self.assertNotIn(CAR["vin"], repr(events[0].data))

        await self.coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(len(events), 2)

        # A restarted coordinator reads the stored starts instead of announcing the same trips again.
        restarted = PleosCoordinator(self.hass, self.entry, self.client)
        self.addAsyncCleanup(restarted.async_shutdown)
        await restarted._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(len(events), 2)

        third = {"triggerStartTime": stamp(10), "tripLength": 500}
        self.serve_trips(first, second, third)
        restarted.trips.cache.clear()
        await restarted._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual([event.data["trip_start"] for event in events[2:]], [third["triggerStartTime"]])

    async def test_trip_event_carries_device_id_when_registered(self):
        events = self.capture_trip_events()
        car_id = vehicle_id("kia", CAR["vin"])
        device = device_registry.async_get(self.hass).async_get_or_create(
            config_entry_id=self.entry.entry_id, identifiers={(DOMAIN, car_id)})
        self.serve_trips({"triggerStartTime": stamp(30)})
        await self.coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(events[0].data["device_id"], device.id)

    async def test_failed_poll_does_not_mark_trips_seen(self):
        events = self.capture_trip_events()
        trip = {"triggerStartTime": stamp(30)}
        payload = {"trips": [trip]}
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: payload if "/speed?" in path
                                    else (_ for _ in ()).throw(AuthError("expired")) if "/status/data?" in path else None)
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(events, [])
        self.serve_trips(trip)
        await self.coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(len(events), 1)

    async def test_same_start_on_another_endpoint_is_a_separate_event(self):
        events = self.capture_trip_events()
        start = stamp(30)
        payload = {"trips": [{"triggerStartTime": start}]}
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: payload if "/speed?" in path or "/driving/data?" in path else None)
        await self.coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(sorted(event.data["endpoint"] for event in events), ["driving/data", "speed"])

    async def test_removing_entry_forgets_announced_trips(self):
        self.serve_trips({"triggerStartTime": stamp(30)})
        await self.coordinator._async_update_data()
        self.assertTrue(await self.coordinator.trips.store.async_load())
        await async_remove_entry(self.hass, self.entry)
        self.assertIsNone(await self.coordinator.trips.store.async_load())

    async def test_trip_endpoints_use_their_own_interval_and_keep_readings(self):
        trip = {"triggerStartTime": stamp(30), "location": {"speed": [42], "speedUnit": ["kph"]}}
        self.serve_trips(trip)
        await self.coordinator._async_update_data()
        self.assertEqual(self.client.get.await_count, 10)

        # Within the trip interval only the six snapshot endpoints are queried.
        self.client.get.reset_mock()
        result = await self.coordinator._async_update_data()
        queried = [call.args[0] for call in self.client.get.await_args_list]
        self.assertEqual(len(queried), 6)
        self.assertFalse(any("?" in path for path in queried))
        car = next(iter(result["cars"].values()))
        self.assertEqual(car["readings"]["speed_location_speed"]["value"], 42)
        self.assertEqual(car["readings"]["speed_api"]["value"], "available")
        self.assertEqual(car["sources"]["speed"], trip["triggerStartTime"])
        self.assertEqual(car["readings"]["driving_data_api"]["value"], "no_data")

        # Once the interval has passed, trips are fetched again.
        for cached in self.coordinator.trips.cache.values():
            cached["fetched_at"] -= timedelta(minutes=60)
        self.client.get.reset_mock()
        await self.coordinator._async_update_data()
        self.assertEqual(self.client.get.await_count, 10)

    async def test_trip_interval_option_and_new_vehicles_are_fetched_at_once(self):
        self.hass.config_entries.async_update_entry(self.entry, options={"trip_poll_minutes": 5})
        coordinator = PleosCoordinator(self.hass, self.entry, self.client)
        self.addAsyncCleanup(coordinator.async_shutdown)
        self.serve_trips()
        await coordinator._async_update_data()
        for cached in coordinator.trips.cache.values():
            cached["fetched_at"] -= timedelta(minutes=5)
        other = CAR | {"vin": "SYNTHETIC-CAR-002"}
        self.client.vehicles = AsyncMock(return_value=[CAR, other])
        self.client.get.reset_mock()
        await coordinator._async_update_data()
        self.assertEqual(self.client.get.await_count, 20)
        self.client.get.reset_mock()
        await coordinator._async_update_data()
        self.assertEqual(self.client.get.await_count, 12)

    async def test_rate_limited_poll_does_not_refresh_trip_cache(self):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: (_ for _ in ()).throw(ApiError(429, "429"))
                                    if "/batteries" in path else None)
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.trips.cache, {})
        self.client.get = AsyncMock(return_value=None)
        await self.coordinator._async_update_data()
        self.assertEqual(self.client.get.await_count, 10)

    async def test_trip_events_can_be_disabled(self):
        events = self.capture_trip_events()
        self.hass.config_entries.async_update_entry(self.entry, options={"trip_events": False})
        coordinator = PleosCoordinator(self.hass, self.entry, self.client)
        self.addAsyncCleanup(coordinator.async_shutdown)
        self.serve_trips({"triggerStartTime": stamp(30), "location": {"speed": [10], "speedUnit": ["kph"]}})
        result = await coordinator._async_update_data()
        await self.hass.async_block_till_done()
        self.assertEqual(events, [])
        self.assertIn("speed_location_speed", next(iter(result["cars"].values()))["readings"])
        self.assertIsNone(await coordinator.trips.store.async_load())


if __name__ == "__main__":
    unittest.main()
