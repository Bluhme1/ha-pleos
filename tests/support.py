"""Shared fixtures for the tests: synthetic vehicles and a Home Assistant test case."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry

from custom_components.pleos_vehicle_data.api import PleosClient
from custom_components.pleos_vehicle_data.config_flow import PleosConfigFlow
from custom_components.pleos_vehicle_data.const import DOMAIN, TRIP_EVENT
from custom_components.pleos_vehicle_data.coordinator import PleosCoordinator

CAR = {"vin": "SYNTHETIC-CAR-001", "sellname": "Example EV", "type": "EV"}

OLD = {"brand": "kia", "client_id": "fixture-old-id", "client_secret": "fixture-old-secret"}

NEW = {"client_id": "fixture-new-id", "client_secret": "fixture-new-secret"}


def entry(data=None):
    return config_entries.ConfigEntry(
        data=data or OLD, domain=DOMAIN, title="Kia", unique_id="kia", version=1,
        minor_version=1, source="user", options={}, discovery_keys={}, subentries_data=[],
        state=config_entries.ConfigEntryState.SETUP_IN_PROGRESS,
    )


def stamp(minutes=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


class HomeAssistantTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = config_entries.ConfigEntries(self.hass, {})
        self.entry = entry()
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        # Home Assistant always provides the device registry; trip events look devices up in it.
        self.hass.data[device_registry.DATA_REGISTRY] = device_registry.DeviceRegistry(self.hass)
        await device_registry.async_load(self.hass, load_empty=True)
        self.client = PleosClient(MagicMock(), **OLD)
        self.coordinator = PleosCoordinator(self.hass, self.entry, self.client)
        self.session_patch = patch("custom_components.pleos_vehicle_data.config_flow.async_get_clientsession", return_value=MagicMock())
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    async def asyncTearDown(self):
        await self.coordinator.async_shutdown()
        await self.hass.async_stop()
        self.temp.cleanup()

    def flow(self, source="user"):
        flow = PleosConfigFlow()
        flow.hass = self.hass
        flow.context = {"source": source, "entry_id": self.entry.entry_id}
        return flow

    async def populate(self, data=None):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(return_value=data or {"timestamp": stamp(), "charge": {"stateOfCharge": 50, "charging": False}})
        self.coordinator.data = await self.coordinator._async_update_data()
        self.coordinator.last_update_success = True

    def capture_trip_events(self):
        events = []
        # A plain function listener runs in the executor, so its call order is not guaranteed.
        self.addCleanup(self.hass.bus.async_listen(TRIP_EVENT, callback(lambda event: events.append(event))))
        return events

    def serve_trips(self, *trips, endpoint="speed"):
        payload = {"trips": list(trips)}
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: payload if f"/{endpoint}?" in path else None)
        return payload
