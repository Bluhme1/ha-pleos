"""The diagnostics download contains the integration's state without personal data."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.pleos_vehicle_data.const import DOMAIN
from custom_components.pleos_vehicle_data.data import vehicle_id
from custom_components.pleos_vehicle_data.diagnostics import (async_get_config_entry_diagnostics,
                                                             async_get_device_diagnostics)

from support import CAR, OLD, HomeAssistantTestCase, stamp

VIN = CAR["vin"]


class DiagnosticsTests(HomeAssistantTestCase):
    async def populate_everything(self):
        car = CAR | {"nickname": "Family van", "modelYear": 2026}
        self.client.vehicles = AsyncMock(return_value=[car])
        self.client.response_meta = {f"/v1/vehicles/{VIN}/batteries": {"requestId": "req-1", "note": f"car {VIN}"}}

        def get(path):
            if "/locations" in path:
                return {"timestamp": stamp(), "location": {"type": 0, "latitude": 48.137, "longitude": 11.575,
                                                            "altitude": 520}}
            if "/batteries" in path:
                return {"timestamp": stamp(), "charge": {"stateOfCharge": 64}, "echo": VIN}
            if "/speed?" in path:
                return {"trips": [{"triggerStartTime": stamp(30), "location": {"speed": [40], "speedUnit": ["kph"]}}]}
            return None
        self.client.get = AsyncMock(side_effect=get)
        self.coordinator.data = await self.coordinator._async_update_data()
        self.coordinator.last_update_success = True
        self.entry.runtime_data = self.coordinator

    async def test_entry_diagnostics_cover_state_and_hide_personal_data(self):
        await self.populate_everything()
        diagnostics = await async_get_config_entry_diagnostics(self.hass, self.entry)
        text = json.dumps(diagnostics)  # Must be serialisable as it is.
        for secret in (VIN, OLD["client_id"], OLD["client_secret"], "Family van", "48.137", "11.575"):
            self.assertNotIn(secret, text)
        self.assertEqual(diagnostics["entry"]["data"]["brand"], "kia")
        self.assertEqual(diagnostics["coordinator"]["status"], "connected")
        self.assertIn("max_query_days", diagnostics["trips"])
        self.assertEqual(diagnostics["archive"]["enabled"], True)
        self.assertEqual(diagnostics["archive"]["status"]["state"], "ok")
        car = diagnostics["cars"][vehicle_id("kia", VIN)]
        self.assertEqual(car["readings"]["batteries_charge_stateofcharge"]["value"], 64)
        self.assertEqual(car["readings"]["locations_location_latitude"]["value"], "**REDACTED**")
        self.assertEqual(car["readings"]["locations_location_altitude"]["value"], 520)
        self.assertEqual(car["readings"]["vehicle_information"]["attributes"]["model_year"], 2026)
        self.assertEqual(car["readings"]["batteries_api"]["attributes"]["data"]["echo"], "**REDACTED**")
        self.assertEqual(diagnostics["coordinator"]["api_metadata"][0]["note"], "car **REDACTED**")

    async def test_device_diagnostics_return_one_car_or_the_account(self):
        await self.populate_everything()
        car_id = vehicle_id("kia", VIN)
        car = await async_get_device_diagnostics(self.hass, self.entry, SimpleNamespace(identifiers={(DOMAIN, car_id)}))
        self.assertEqual(car["vehicle_id"], car_id)
        self.assertNotIn(VIN, json.dumps(car))
        account = await async_get_device_diagnostics(self.hass, self.entry, SimpleNamespace(identifiers={(DOMAIN, "kia_api")}))
        self.assertNotIn("cars", account)
        self.assertIn("coordinator", account)

    async def test_diagnostics_before_the_first_successful_poll(self):
        self.entry.runtime_data = self.coordinator
        diagnostics = await async_get_config_entry_diagnostics(self.hass, self.entry)
        json.dumps(diagnostics)
        self.assertEqual(diagnostics["cars"], {})
