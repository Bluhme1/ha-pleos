"""Setup, reauthentication, reconfiguration and options flows."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import probatio
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv, device_registry as dr

from custom_components.pleos_vehicle_data import async_setup_entry
from custom_components.pleos_vehicle_data.api import AuthError, PleosClient
from custom_components.pleos_vehicle_data.config_flow import PleosOptionsFlow
from custom_components.pleos_vehicle_data.const import BRANDS, DOMAIN
from custom_components.pleos_vehicle_data.data import vehicle_id
from custom_components.pleos_vehicle_data.sensor import ConnectionSensor

from support import CAR, HomeAssistantTestCase, NEW, OLD


class ConfigFlowTests(HomeAssistantTestCase):
    async def test_coordinator_stops_polling_and_starts_native_reauth(self):
        await self.populate()
        self.client.vehicles.side_effect = AuthError()
        with patch.object(self.entry, "async_start_reauth_if_available") as reauth, patch.object(self.coordinator, "_schedule_refresh") as schedule:
            await self.coordinator.async_refresh()
            reauth.assert_called_once_with(self.hass)
            schedule.assert_not_called()
        self.assertIsInstance(self.coordinator.last_exception, ConfigEntryAuthFailed)
        self.assertEqual(ConnectionSensor(self.coordinator).native_value, "key_required")

    async def test_reauth_validates_and_preserves_entry(self):
        flow = self.flow("reauth")
        with patch.object(flow, "_get_reauth_entry", return_value=self.entry), patch.object(PleosClient, "vehicles", AsyncMock(return_value=[CAR])), patch.object(self.hass.config_entries, "async_schedule_reload") as reload:
            result = await flow.async_step_reauth_confirm(NEW)
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertEqual(self.entry.data, OLD | NEW)
        self.assertEqual(self.entry.unique_id, "kia")
        reload.assert_called_once_with(self.entry.entry_id)

    async def test_rejected_replacement_keeps_previous_credentials(self):
        flow = self.flow("reauth")
        with patch.object(flow, "_get_reauth_entry", return_value=self.entry), patch.object(PleosClient, "vehicles", AsyncMock(side_effect=AuthError())):
            result = await flow.async_step_reauth_confirm(NEW)
        self.assertEqual(result["errors"], {"base": "invalid_auth"})
        self.assertEqual(self.entry.data, OLD)

    async def test_proactive_key_replacement(self):
        flow = self.flow("reconfigure")
        with patch.object(flow, "_get_reconfigure_entry", return_value=self.entry), patch.object(PleosClient, "vehicles", AsyncMock(return_value=[CAR])), patch.object(self.hass.config_entries, "async_schedule_reload"):
            result = await flow.async_step_reconfigure(NEW)
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(self.entry.data["client_id"], NEW["client_id"])

    async def test_user_flow_for_all_brands_and_secret_selector(self):
        with patch.object(PleosClient, "vehicles", AsyncMock(return_value=[CAR])):
            for brand in BRANDS:
                flow = self.flow()
                with patch.object(flow, "_abort_if_unique_id_configured"):
                    result = await flow.async_step_user(NEW | {"brand": brand})
                self.assertEqual(result["type"], "create_entry")
                self.assertEqual(result["data"]["brand"], brand)
        result = await self.flow().async_step_user()
        selector = next(v for k, v in result["data_schema"].schema.items() if str(k) == "client_secret")
        self.assertEqual(selector.config["type"], "password")

    async def test_options_and_limits(self):
        flow = PleosOptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        form = await flow.async_step_init()
        submitted = form["data_schema"]({"polling": {"poll_minutes": 20, "stale_minutes": 60, "location": False},
                                         "trips": {}, "storage": {}})
        self.assertEqual(submitted["polling"]["poll_minutes"], 20)
        # Unchanged fields keep their defaults inside each section.
        self.assertEqual(submitted["trips"], {"trip_poll_minutes": 60, "trip_events": True})
        for invalid in ({"poll_minutes": 1}, {"stale_minutes": 10081}):
            with self.subTest(invalid=invalid), self.assertRaises(Exception):
                form["data_schema"]({"polling": {"poll_minutes": 15, "stale_minutes": 60, "location": True} | invalid,
                                     "trips": {}, "storage": {}})
        self.assertTrue(flow.automatic_reload)
        # The frontend receives two expanded sections with their fields.
        fields = probatio.to_field_list(form["data_schema"], custom_serializer=cv.custom_serializer)
        self.assertEqual([(field["name"], field["type"], field["expanded"]) for field in fields],
                         [("polling", "expandable", True), ("trips", "expandable", True), ("storage", "expandable", True)])
        self.assertEqual([item["name"] for item in fields[0]["schema"]],
                         ["poll_minutes", "stale_minutes", "location", "odometer_km_vehicles"])

        # Saved options stay flat, so the coordinator and existing entries read them unchanged.
        result = await flow.async_step_init(submitted)
        self.assertEqual(result["data"], {"poll_minutes": 20, "stale_minutes": 60, "location": False,
                                          "trip_poll_minutes": 60, "trip_events": True, "archive": True,
                                          "odometer_km_vehicles": []})

    async def test_options_form_shows_saved_values(self):
        self.hass.config_entries.async_update_entry(self.entry, options={"poll_minutes": 30, "trip_events": False})
        flow = PleosOptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        defaults = (await flow.async_step_init())["data_schema"]({"polling": {}, "trips": {}, "storage": {}})
        self.assertEqual(defaults, {"polling": {"poll_minutes": 30, "stale_minutes": 60, "location": True,
                                               "odometer_km_vehicles": []},
                                    "trips": {"trip_poll_minutes": 60, "trip_events": False},
                                    "storage": {"archive": False}})

    async def test_odometer_correction_selects_account_cars_and_preserves_missing_car(self):
        car_id = vehicle_id("kia", CAR["vin"])
        missing_id = vehicle_id("kia", "SYNTHETIC-MISSING-CAR")
        self.hass.config_entries.async_update_entry(self.entry, options={"odometer_km_vehicles": [missing_id]})
        registry = dr.async_get(self.hass)
        device = registry.async_get_or_create(config_entry_id=self.entry.entry_id,
                                              identifiers={(DOMAIN, car_id)}, name="Example EV")
        registry.async_update_device(device.id, name_by_user="Family car")
        registry.async_get_or_create(config_entry_id=self.entry.entry_id,
                                     identifiers={(DOMAIN, "kia_api")}, name="Kia API")
        flow = PleosOptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        form = await flow.async_step_init()
        fields = probatio.to_field_list(form["data_schema"], custom_serializer=cv.custom_serializer)
        field = next(item for item in fields[0]["schema"] if item["name"] == "odometer_km_vehicles")
        choices = field["selector"]["select"]["options"]
        self.assertEqual({item["value"] for item in choices}, {car_id, missing_id})
        self.assertIn({"value": car_id, "label": f"Family car ({car_id[-6:]})"}, choices)
        defaults = form["data_schema"]({"polling": {}, "trips": {}, "storage": {}})
        self.assertEqual(defaults["polling"]["odometer_km_vehicles"], [missing_id])
        with self.assertRaises(Exception):
            form["data_schema"]({"polling": {"odometer_km_vehicles": ["kia_api"]}, "trips": {}, "storage": {}})
        for selected in ([car_id], []):
            submitted = form["data_schema"]({"polling": {"odometer_km_vehicles": selected}, "trips": {}, "storage": {}})
            result = await flow.async_step_init(submitted)
            self.assertEqual(result["data"]["odometer_km_vehicles"], selected)

    async def test_setup_uses_replacement_credentials_and_fresh_token(self):
        self.hass.config_entries.async_update_entry(self.entry, data=OLD | NEW)
        with patch("custom_components.pleos_vehicle_data.async_get_clientsession", return_value=MagicMock()), patch.object(PleosClient, "vehicles", AsyncMock(return_value=[])), patch.object(self.hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
        self.assertEqual(self.entry.runtime_data.client.credentials["clientId"], NEW["client_id"])
        self.assertIsNone(self.entry.runtime_data.client.token)
        await self.entry.runtime_data.async_shutdown()


    async def test_raw_exports_are_opt_in_for_new_entries(self):
        self.hass.config_entries.async_update_entry(self.entry, options={})
        flow = PleosOptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        defaults = (await flow.async_step_init())["data_schema"]({"polling": {}, "trips": {}, "storage": {}})
        self.assertFalse(defaults["trips"]["trip_events"])
        self.assertFalse(defaults["storage"]["archive"])


if __name__ == "__main__":
    unittest.main()
