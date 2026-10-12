"""Synthetic checks using Home Assistant's real classes, without network calls."""

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.helpers import device_registry, entity_registry

from custom_components.pleos_vehicle_data import async_setup_entry
from custom_components.pleos_vehicle_data.api import ApiError, AuthError, PleosClient
from custom_components.pleos_vehicle_data.binary_sensor import ReadingBinarySensor
from custom_components.pleos_vehicle_data.config_flow import PleosConfigFlow, PleosOptionsFlow
from custom_components.pleos_vehicle_data.const import BRANDS, DOMAIN, ENDPOINTS
from custom_components.pleos_vehicle_data.coordinator import PleosCoordinator
from custom_components.pleos_vehicle_data.data import TRIP_FIELDS, TRIP_NAMES, location, readings, trip_readings, vehicle_id
from custom_components.pleos_vehicle_data.device_tracker import VehicleTracker
from custom_components.pleos_vehicle_data.entity import discover
from custom_components.pleos_vehicle_data.sensor import ConnectionSensor, ReadingSensor

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


class DataTests(unittest.TestCase):
    def test_ev_hybrid_and_combustion(self):
        sample = {"engine": {"fuelLevel": 0}, "distanceToEmpties": [{"type": "EV", "value": "106", "unit": "km"}]}
        self.assertNotIn("powertrains_engine_fuellevel", readings("powertrains", sample, "EV"))
        for kind in ("GN", "HV", "PE", "UNKNOWN"):
            self.assertEqual(readings("powertrains", sample, kind)["powertrains_engine_fuellevel"]["value"], 0)
        self.assertEqual(readings("powertrains", sample, "EV")["powertrains_distancetoempties_ev"]["value"], 106)

    def test_absent_and_invalid_values_are_omitted(self):
        self.assertEqual(readings("status", {"outsideTemperature": {"unit": "C"}, "hood": None, "trunk": "invalid"}, "EV"), {})
        self.assertEqual(readings("batteries", {"charge": {"stateOfCharge": 101, "remainTime": 65536, "batteryCapacity": float("nan")}}, "EV"), {})
        self.assertEqual(readings("batteries", {"charge": {"remainTime": 65535}}, "EV")["batteries_charge_remaintime"]["value"], 65535)

    def test_zero_false_and_tyre_units(self):
        sample = readings("batteries", {"charge": {"stateOfCharge": 0, "charging": False, "plugin": "disconnected"}}, "EV")
        self.assertEqual(sample["batteries_charge_stateofcharge"]["value"], 0)
        self.assertEqual(sample["batteries_charge_charging"]["value"], "OFF")
        self.assertEqual(sample["batteries_charge_plugin"]["value"], "OFF")
        for unit, raw, expected in (("psi", 52, 52), ("kpa", 72, 360), ("bar", 36, 3.6)):
            values = readings("status", {"tire": [{"left": raw, "right": 255, "unit": unit}]}, "EV")
            self.assertEqual(values["status_tire_row1_left"]["value"], expected)
            self.assertNotIn("status_tire_row1_right", values)

    def test_location_validation_and_zero_coordinates(self):
        for point in ({"latitude": 0, "longitude": 0, "type": 1}, {"latitude": 100, "longitude": 0, "type": 0}, {"latitude": True, "longitude": 0, "type": 0}):
            self.assertIsNone(location({"location": point, "timestamp": stamp()}))
        self.assertEqual(location({"location": {"latitude": 0, "longitude": 0, "type": 0}, "timestamp": stamp()})["latitude"], 0)

    def test_vehicle_identity_is_stable_and_does_not_contain_vin(self):
        for brand in BRANDS:
            self.assertEqual(vehicle_id(brand, CAR["vin"]), vehicle_id(brand, CAR["vin"]))
            self.assertNotIn(CAR["vin"], vehicle_id(brand, CAR["vin"]))

    def test_freezer_and_all_location_fields(self):
        freezer = readings("freezer", {"freezer": {"status": "on", "temperature": -20}}, "EV")
        self.assertEqual(freezer["freezer_freezer_temperature"]["unit_of_measurement"], "°C")
        self.assertNotIn("freezer_freezer_temperature", readings("freezer", {"freezer": {"temperature": 63}}, "EV"))
        values = readings("locations", {"location": {"latitude": 0, "longitude": 0, "altitude": -1, "heading": 359, "speed": {"value": 10, "unit": "kph"}}}, "EV")
        self.assertEqual(len(values), 5)
        self.assertEqual(values["locations_location_speed"]["device_class"], "speed")

    def test_readable_labels_preserve_data_keys(self):
        values = readings("status", {"doors": [{"left": "locked"}],
                                    "seats": [{"right": {"heat": "off"}}],
                                    "climateControl": {"speed": 2, "temperature": {"value": 20, "unit": "C"}}}, "EV")
        expected = {"status_doors_row1_left": "Front left door",
                    "status_seats_row1_right_heat": "Front right seat heating",
                    "status_climatecontrol_speed": "Cabin fan speed",
                    "status_climatecontrol_temperature": "Cabin target temperature"}
        self.assertEqual({key: value["name"] for key, value in values.items()}, expected)
        self.assertEqual(set(TRIP_NAMES), {field for fields in TRIP_FIELDS.values() for field in fields})

    def test_trip_units_and_latest_trip_selection(self):
        old = {"triggerStartTime": stamp(120), "tripLength": 1000, "engine": {"rpm": [1]}}
        recent = {"triggerStartTime": stamp(60), "tripLength": 2500,
                  "batteries": {"hv": {"voltage": [250, 251]}},
                  "engine": {"oilTemperature": [20, 21], "rpm": [100, 200]}}
        values, start = trip_readings("powertrains/data", {"trips": [recent, old]})
        self.assertEqual(start, recent["triggerStartTime"])
        self.assertEqual(values["powertrains_data_engine_rpm"]["value"], 200)
        self.assertEqual(values["powertrains_data_engine_rpm"]["name"], "Engine speed (last trip)")
        self.assertEqual(values["powertrains_data_batteries_hv_voltage"]["unit_of_measurement"], "V")
        self.assertEqual(values["powertrains_data_trip_duration"]["value"], 2.5)

    def test_trip_pressure_alignment_and_invalid_last_sample(self):
        trip = {"triggerStartTime": stamp(), "tripLength": 3000,
                "tire": {"pressureFrontLeft": [50, 72], "pressureFrontRight": [50, 255], "pressureUnit": ["psi", "kpa"]},
                "outsideTemperature": {"value": [10, None]}}
        values, _ = trip_readings("status/data", {"trips": [trip]})
        self.assertEqual(values["status_data_tire_pressurefrontleft"]["value"], 360)
        self.assertNotIn("status_data_tire_pressurefrontright", values)
        self.assertNotIn("status_data_outsidetemperature_value", values)
        speeds, _ = trip_readings("speed", {"trips": [{"triggerStartTime": stamp(), "location": {"speed": [1, 2], "speedUnit": ["kph"]}}]})
        self.assertNotIn("speed_location_speed", speeds)


class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = config_entries.ConfigEntries(self.hass, {})
        self.entry = entry()
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
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

    async def test_short_lived_token_refreshes_once(self):
        self.client._request = AsyncMock(side_effect=[{"accessToken": "old"}, ApiError(400, "40003"), {"accessToken": "new"}, {"vehicles": []}])
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(self.client._request.await_count, 4)
        self.assertEqual(self.client.token, "new")

    async def test_expired_token_403_refreshes_and_reuses_new_token(self):
        self.client.token = "expired-fixture-token"
        def response(status, payload):
            result = MagicMock()
            result.status = status
            async def chunks(size):
                yield json.dumps(payload).encode()
            result.content.iter_chunked = chunks
            context = MagicMock()
            context.__aenter__.return_value = result
            return context
        self.client.session.request.side_effect = [
            response(403, {"error": {"code": 403}}),
            response(200, {"data": {"accessToken": "renewed-fixture-token"}}),
            response(200, {"data": {"vehicles": []}}),
            response(200, {"data": {"vehicles": []}}),
        ]
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(self.client.token, "renewed-fixture-token")
        requests = self.client.session.request.call_args_list
        self.assertEqual([call.args[0] for call in requests], ["GET", "POST", "GET", "GET"])
        self.assertEqual(requests[0].kwargs["headers"]["Authorization"], "Bearer expired-fixture-token")
        self.assertEqual(requests[2].kwargs["headers"]["Authorization"], "Bearer renewed-fixture-token")

    async def test_persistent_403_is_permission_error_and_keeps_fresh_token(self):
        self.client.token = "old"
        self.client._request = AsyncMock(side_effect=[ApiError(403, "403"), {"accessToken": "fresh"}, ApiError(403, "403"), {"vehicles": []}])
        with self.assertRaises(ApiError) as caught:
            await self.client.get("/v1/vehicles/SYNTHETIC-CAR-001/locations")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(self.client._request.await_count, 3)
        self.assertEqual(self.client.token, "fresh")
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(self.client._request.await_count, 4)

    async def test_expired_key_after_403_requires_reauth(self):
        self.client.token = "expired"
        self.client._request = AsyncMock(side_effect=[ApiError(403, "403"), ApiError(404, "40404")])
        with self.assertRaises(AuthError):
            await self.client.vehicles()
        self.assertEqual(self.client._request.await_count, 2)

    async def test_invalid_key_requires_reauth(self):
        self.client._request = AsyncMock(side_effect=ApiError(404, "40404"))
        with self.assertRaises(AuthError):
            await self.client.vehicles()
        self.assertEqual(self.client._request.await_count, 1)

    async def test_repeated_token_rejection_stops_retry(self):
        self.client._request = AsyncMock(side_effect=[{"accessToken": "one"}, ApiError(400, "4011"), {"accessToken": "two"}, ApiError(400, "4011")])
        with self.assertRaises(AuthError):
            await self.client.vehicles()
        self.assertEqual(self.client._request.await_count, 4)

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
        self.assertEqual(form["data_schema"]({"poll_minutes": 15, "stale_minutes": 60, "location": True})["poll_minutes"], 15)
        with self.assertRaises(Exception):
            form["data_schema"]({"poll_minutes": 1, "stale_minutes": 60, "location": True})
        self.assertTrue(flow.automatic_reload)

    async def test_stale_missing_and_binary_values(self):
        await self.populate()
        car_id = vehicle_id("kia", CAR["vin"])
        spec = self.coordinator.data["cars"][car_id]["readings"]["batteries_charge_stateofcharge"]
        sensor = ReadingSensor(self.coordinator, car_id, "batteries_charge_stateofcharge", spec)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 50)
        self.coordinator.data["cars"][car_id]["sources"]["batteries"] = stamp(120)
        self.assertFalse(sensor.available)
        diagnostic_spec = self.coordinator.data["cars"][car_id]["readings"]["batteries_reported_at"]
        diagnostic = ReadingSensor(self.coordinator, car_id, "batteries_reported_at", diagnostic_spec)
        self.assertTrue(diagnostic.available)
        self.assertIsNotNone(diagnostic.native_value.tzinfo)
        spec = self.coordinator.data["cars"][car_id]["readings"]["batteries_charge_charging"]
        self.assertFalse(ReadingBinarySensor(self.coordinator, car_id, "batteries_charge_charging", spec).is_on)
        del self.coordinator.data["cars"][car_id]["readings"][sensor.key]
        self.assertFalse(sensor.available)

    async def test_partial_endpoint_and_network_failure(self):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=[ApiError(404, "4045"), {"timestamp": stamp(), "engine": {"fuelLevel": 20}}, *([None] * 8)])
        result = await self.coordinator._async_update_data()
        self.assertEqual(len(result["cars"]), 1)
        self.assertTrue(next(iter(result["cars"].values()))["readings"])
        self.client.get = AsyncMock(side_effect=ApiError(0, "connection_failed"))
        with self.assertRaises(UpdateFailed):
            await self.coordinator._async_update_data()

    async def test_dynamic_discovery_has_no_duplicates(self):
        await self.populate()
        self.entry.runtime_data = self.coordinator
        added = MagicMock()
        discover(self.entry, added, "sensor", ReadingSensor)
        first = added.call_count
        self.coordinator.async_update_listeners()
        self.assertEqual(added.call_count, first)
        car_id = vehicle_id("kia", CAR["vin"])
        self.coordinator.data["cars"][car_id]["readings"]["new_field"] = {"name": "New", "source": "status", "value": "open", "domain": "sensor"}
        self.coordinator.async_update_listeners()
        self.assertEqual(added.call_count, first + 1)

    async def test_native_tracker_and_location_opt_out(self):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=[None, None, None, None, {
            "timestamp": stamp(), "location": {"type": 0, "latitude": 0, "longitude": 0},
        }, *([None] * 5)])
        self.coordinator.data = await self.coordinator._async_update_data()
        self.coordinator.last_update_success = True
        car_id = vehicle_id("kia", CAR["vin"])
        tracker = VehicleTracker(self.coordinator, car_id, "location", {"name": "Location", "source": "locations"})
        self.assertTrue(tracker.available)
        self.assertEqual((tracker.latitude, tracker.longitude), (0, 0))
        self.coordinator.data["cars"][car_id]["sources"]["locations"] = stamp(120)
        self.assertFalse(tracker.available)
        self.coordinator.options["location"] = False
        self.client.get = AsyncMock(return_value=None)
        result = await self.coordinator._async_update_data()
        self.assertEqual(self.client.get.await_count, 9)
        self.assertIsNone(result["cars"][car_id]["location"])

    async def test_diagnostics_register_with_native_entity_category(self):
        await self.populate()
        self.hass.data[device_registry.DATA_REGISTRY] = device_registry.DeviceRegistry(self.hass)
        await device_registry.async_load(self.hass, load_empty=True)
        registry = entity_registry.EntityRegistry(self.hass)
        await registry.async_load(load_empty=True)
        car_id = vehicle_id("kia", CAR["vin"])
        for key, spec in self.coordinator.data["cars"][car_id]["readings"].items():
            if spec["domain"] == "sensor":
                sensor = ReadingSensor(self.coordinator, car_id, key, spec)
                registered = registry.async_get_or_create(
                    "sensor", DOMAIN, sensor.unique_id, config_entry=self.entry,
                    entity_category=sensor.entity_category,
                )
                self.assertEqual(registered.entity_category, sensor.entity_category)

    async def test_all_ten_endpoints_and_date_queries(self):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(return_value=None)
        result = await self.coordinator._async_update_data()
        paths = [call.args[0].split("/")[-1] for call in self.client.get.await_args_list]
        self.assertEqual(len(paths), 10)
        queried = [call.args[0].split(CAR["vin"] + "/", 1)[1] for call in self.client.get.await_args_list]
        for endpoint in ("batteries", "powertrains", "driving", "status", "locations", "freezer"):
            self.assertIn(endpoint, queried)
        for endpoint in ("powertrains/data", "speed", "driving/data", "status/data"):
            request = next(path for path in queried if path.startswith(endpoint + "?"))
            self.assertIn("startDate=", request)
            self.assertIn("endDate=", request)
            self.assertIn("zoneId=UTC", request)
        car = next(iter(result["cars"].values()))
        self.assertEqual(sum(key.endswith("_api") for key in car["readings"]), 10)

    async def test_full_trip_data_is_retained_and_not_recorded(self):
        payload = {"trips": [{"triggerStartTime": stamp(240), "tripLength": 2000,
                              "location": {"speed": [10, 20], "speedUnit": ["kph", "kph"]}}]}
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: payload if "/speed?" in path else None)
        self.coordinator.data = await self.coordinator._async_update_data()
        self.coordinator.last_update_success = True
        car_id = vehicle_id("kia", CAR["vin"])
        car = self.coordinator.data["cars"][car_id]
        source = ReadingSensor(self.coordinator, car_id, "speed_api", car["readings"]["speed_api"])
        self.assertEqual(source.extra_state_attributes["data"], payload)
        self.assertIn("data", source._unrecorded_attributes)
        field = ReadingSensor(self.coordinator, car_id, "speed_location_speed", car["readings"]["speed_location_speed"])
        self.assertTrue(field.available)
        self.assertEqual(field.native_value, 20)
        self.assertNotIn("reported_at", field.extra_state_attributes)

    async def test_optional_endpoint_server_error_does_not_hide_status(self):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: {"timestamp": stamp(), "charge": {"stateOfCharge": 50}} if path.endswith("/batteries") else None)
        original_get = self.client.get.side_effect
        def response(path):
            if "/status/data?" in path:
                raise ApiError(500, "5000")
            return original_get(path)
        self.client.get.side_effect = response
        result = await self.coordinator._async_update_data()
        car = next(iter(result["cars"].values()))
        self.assertEqual(car["readings"]["batteries_charge_stateofcharge"]["value"], 50)
        self.assertEqual(car["readings"]["status_data_api"]["value"], "error")

    async def test_optional_permission_error_does_not_hide_status(self):
        self.client.vehicles = AsyncMock(return_value=[CAR])
        def response(path):
            if path.endswith("/locations"):
                raise ApiError(403, "403")
            return {"timestamp": stamp(), "charge": {"stateOfCharge": 50}} if path.endswith("/batteries") else None
        self.client.get = AsyncMock(side_effect=response)
        result = await self.coordinator._async_update_data()
        car = next(iter(result["cars"].values()))
        self.assertEqual(car["readings"]["batteries_charge_stateofcharge"]["value"], 50)
        self.assertEqual(car["readings"]["locations_api"]["value"], "no_data")
        self.assertEqual(car["readings"]["locations_api"]["attributes"]["http_status"], 403)

    async def test_nonfinite_json_is_rejected(self):
        response = MagicMock()
        response.status = 200
        async def chunks(size):
            yield b'{"data": {"temperature": NaN}}'
        response.content.iter_chunked = chunks
        self.client.session.request.return_value.__aenter__.return_value = response
        with self.assertRaises(ApiError) as caught:
            await self.client._request("/v1/auth/personal-token", self.client.credentials)
        self.assertEqual(caught.exception.code, "invalid_response")

    async def test_setup_uses_replacement_credentials_and_fresh_token(self):
        self.hass.config_entries.async_update_entry(self.entry, data=OLD | NEW)
        with patch("custom_components.pleos_vehicle_data.async_get_clientsession", return_value=MagicMock()), patch.object(PleosClient, "vehicles", AsyncMock(return_value=[])), patch.object(self.hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(self.hass, self.entry)
        self.assertEqual(self.entry.runtime_data.client.credentials["clientId"], NEW["client_id"])
        self.assertIsNone(self.entry.runtime_data.client.token)
        await self.entry.runtime_data.async_shutdown()

    async def test_rate_limit_does_not_make_network_requests(self):
        self.client.retry_at = time.monotonic() + 300
        with self.assertRaises(ApiError) as caught:
            await self.client._request("/v1/vehicles/consent")
        self.assertEqual(caught.exception.status, 429)
        self.client.session.request.assert_not_called()

    async def test_http_errors_and_rate_limit_header(self):
        response = MagicMock()
        response.status = 429
        response.headers = {"Retry-After": "1200"}
        async def chunks(size):
            yield json.dumps({"meta": {"success": False, "code": "429"}}).encode()
        response.content.iter_chunked = chunks
        self.client.session.request.return_value.__aenter__.return_value = response
        with self.assertRaises(ApiError) as caught:
            await self.client._request("/v1/auth/personal-token", self.client.credentials)
        self.assertEqual(caught.exception.status, 429)
        self.assertGreater(self.client.retry_at, time.monotonic() + 1190)

    async def test_http_schema_and_redirect_boundary(self):
        response = MagicMock()
        response.status = 200
        response.headers = {}
        async def chunks(size):
            yield b'{"meta": "invalid", "data": null}'
        response.content.iter_chunked = chunks
        self.client.session.request.return_value.__aenter__.return_value = response
        with self.assertRaises(ApiError):
            await self.client._request("/v1/auth/personal-token", self.client.credentials)
        self.assertFalse(self.client.session.request.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
