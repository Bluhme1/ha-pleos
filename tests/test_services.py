"""The refresh service."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError

from custom_components.pleos_vehicle_data.const import DOMAIN, SERVICE_REFRESH
from custom_components.pleos_vehicle_data.services import async_setup_services

from support import HomeAssistantTestCase


class ServiceTests(HomeAssistantTestCase):
    def setup_service(self, state=ConfigEntryState.LOADED):
        async_setup_services(self.hass)
        self.entry.runtime_data = self.coordinator
        self.coordinator.async_refresh = AsyncMock()
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
        await self.call(self.entry.entry_id)

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
