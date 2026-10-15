"""The refresh service."""

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError

from custom_components.pleos_vehicle_data.const import DOMAIN, SERVICE_REFRESH
from custom_components.pleos_vehicle_data.services import async_setup_services

from support import HomeAssistantTestCase


class ServiceTests(HomeAssistantTestCase):
    def setup_service(self, state=ConfigEntryState.LOADED):
        async_setup_services(self.hass)
        self.entry.runtime_data = self.coordinator
        self.entry._async_set_state(self.hass, state, None)

    async def call(self, entry_id):
        await self.hass.services.async_call(
            DOMAIN, SERVICE_REFRESH, {"config_entry_id": entry_id}, blocking=True
        )

    async def test_service_is_registered(self):
        self.setup_service()
        self.assertTrue(self.hass.services.has_service(DOMAIN, SERVICE_REFRESH))

    async def test_refresh_updates_the_coordinator(self):
        self.setup_service()
        with patch.object(self.coordinator, "async_request_refresh", new_callable=AsyncMock) as refresh:
            await self.call(self.entry.entry_id)
        refresh.assert_awaited_once_with()

    async def test_concurrent_requests_batch_account_polls(self):
        self.setup_service()
        self.client.vehicles = AsyncMock(return_value=[])
        await asyncio.gather(*(self.call(self.entry.entry_id) for _ in range(5)))
        self.client.vehicles.assert_awaited_once_with()
        self.assertEqual(self.coordinator.data, {"status": "no_vehicles", "cars": {}})

    async def test_unknown_entry_is_rejected(self):
        self.setup_service()
        with self.assertRaises(ServiceValidationError) as raised:
            await self.call("missing")
        self.assertEqual(raised.exception.translation_key, "entry_not_found")

    async def test_unloaded_entry_is_rejected(self):
        self.setup_service(ConfigEntryState.NOT_LOADED)
        with self.assertRaises(ServiceValidationError) as raised:
            await self.call(self.entry.entry_id)
        self.assertEqual(raised.exception.translation_key, "entry_not_loaded")

    async def test_other_domain_entry_is_rejected(self):
        self.setup_service()
        other = type(self.entry)(
            data={},
            domain="other",
            title="Other",
            unique_id="other",
            version=1,
            minor_version=1,
            source="user",
            options={},
            discovery_keys={},
            subentries_data=[],
        )
        self.hass.config_entries._entries[other.entry_id] = other
        with self.assertRaises(ServiceValidationError) as raised:
            await self.call(other.entry_id)
        self.assertEqual(raised.exception.translation_key, "entry_not_found")

    async def test_entry_id_is_required(self):
        self.setup_service()
        with self.assertRaises(Exception):
            await self.hass.services.async_call(
                DOMAIN, SERVICE_REFRESH, {}, blocking=True
            )
