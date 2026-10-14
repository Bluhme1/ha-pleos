"""Pleos Vehicle Data native Home Assistant integration."""

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import PleosClient
from .const import DOMAIN
from .coordinator import PleosCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER]


async def async_setup_entry(hass, entry):
    coordinator = PleosCoordinator(hass, entry, PleosClient(
        async_get_clientsession(hass), entry.data["brand"], entry.data["client_id"], entry.data["client_secret"],
    ))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass, entry):
    # Forget which trips were announced for this account.
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.trips").async_remove()
