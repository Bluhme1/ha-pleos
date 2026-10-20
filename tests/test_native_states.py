"""Native status types, warning availability and charge-limit metadata."""

import json
import logging
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform
from pleos_client import ApiError

from custom_components.pleos_vehicle_data.binary_sensor import ReadingBinarySensor
from custom_components.pleos_vehicle_data.const import DOMAIN
from custom_components.pleos_vehicle_data.data import ENUM_OPTIONS, TRIP_ENUM_OPTIONS, readings, trip_readings, trip_summary, vehicle_id
from custom_components.pleos_vehicle_data.sensor import ReadingSensor

from support import CAR, HomeAssistantTestCase, stamp
from test_names import SNAPSHOTS, trip_payload


class NativeParsingTests(unittest.TestCase):
    def test_fan_modes_and_only_real_measurements_have_statistics(self):
        for raw, expected in ((-1, "auto"), (0, "off"), *((i, f"level_{i}") for i in range(1, 9))):
            reading = readings("status", {"climateControl": {"speed": raw}}, "EV")["status_climatecontrol_speed"]
            self.assertEqual((reading["value"], reading["device_class"]), (expected, "enum"))
            self.assertNotIn("state_class", reading)
        for raw in (-2, 9, 1.5, True, "auto", None):
            self.assertNotIn("status_climatecontrol_speed", readings("status", {"climateControl": {"speed": raw}}, "EV"))
        parsed = {}
        for endpoint, payload in SNAPSHOTS.items():
            parsed |= readings(endpoint, payload, "HV")
        for key in ("batteries_charge_targetstateofcharge_standard", "batteries_charge_targetstateofcharge_quick",
                    "batteries_charge_batterycapacity", "batteries_charge_remaintime",
                    "status_climatecontrol_temperature", "locations_location_latitude", "locations_location_longitude",
                    "powertrains_distancetoempties_ev"):
            self.assertNotIn("state_class", parsed[key], key)
        self.assertNotIn("device_class", parsed["batteries_charge_batterycapacity"])
        self.assertNotIn("unit_of_measurement", parsed["batteries_charge_batterycapacity"])
        self.assertEqual(parsed["driving_odometer"]["state_class"], "total")
        self.assertEqual(parsed["locations_location_heading"]["state_class"], "measurement_angle")
        self.assertEqual(parsed["locations_location_type"]["entity_category"], "diagnostic")
        self.assertEqual(parsed["driving_ignition_status"]["device_class"], "power")
        self.assertEqual(parsed["status_climatecontrol_status"]["device_class"], "running")
        self.assertEqual(parsed["freezer_freezer_status"]["device_class"], "running")
        for key in ("batteries_charge_stateofcharge", "status_outsidetemperature", "status_tire_row1_left"):
            self.assertEqual(parsed[key]["state_class"], "measurement")

    def test_documented_boolean_fields_reject_non_boolean_values(self):
        for endpoint, payload, key in (
            ("batteries", lambda v: {"charge": {"charging": v}}, "batteries_charge_charging"),
            ("driving", lambda v: {"transmission": {"parkingPosition": v}}, "driving_transmission_parkingposition"),
        ):
            for value in (True, False, 0, 1, "true", "false", "on", None, "invalid"):
                parsed = readings(endpoint, payload(value), "EV")
                if isinstance(value, bool):
                    self.assertEqual((parsed[key]["domain"], parsed[key]["value"]),
                                     ("binary_sensor", "ON" if value else "OFF"))
                else:
                    self.assertNotIn(key, parsed)
        future = readings("status", {"newModule": {"remainRatio": 50, "stateOfCharge": 60},
                                     "charge": {"charging": True, "plugin": "connected"}}, "EV")
        self.assertTrue(all("device_class" not in reading for reading in future.values()))

    def test_historical_states_keep_their_meaning_and_invalid_last_samples_stay_missing(self):
        cases = [
            ("driving/data", "ignition.status", {"on": "ON", "off": "OFF"}, "power"),
            *[("status/data", "doors.open" + side, {"open": "ON", "close": "OFF"}, "door")
              for side in ("Assistance", "Driver", "RearLeft", "RearRight")],
            ("status/data", "warnings.lowFuelLevel", {"on": "ON", "off": "OFF"}, "problem"),
            ("driving/data", "seatbelt.driver", {"belted": "belted", "unbelted": "unbelted"}, "enum"),
            ("driving/data", "seatbelt.assistance", {"belted": "belted", "unbelted": "unbelted"}, "enum"),
            ("driving/data", "transmission.gear", {v: v for v in ("p", "r", "n", "d")}, "enum"),
            ("driving/data", "isla.optionUsm", {v: v for v in ("none", "off", "warning", "assist")}, "enum"),
            ("driving/data", "isla.optionUsm2", {v: v for v in ("none", "off", "information", "warning", "assist")}, "enum"),
            ("status/data", "lamp.setting", {"lightSwOff": "off", "tailSwOn": "tail_lights",
                                           "headLampLowSwOn": "headlamps", "autoLightSwOn": "auto"}, "enum"),
            ("speed", "location.speedUnit", {"kph": "kph", "mph": "mph"}, "enum"),
            ("status/data", "tire.pressureUnit", {"psi": "psi", "kpa": "kpa", "bar": "bar"}, "enum"),
        ]
        for endpoint, field, values, device_class in cases:
            for raw in (*values, "invalid", None, "unexpected", True, 1, [], {}):
                with self.subTest(field=field, raw=raw):
                    trip = {"triggerStartTime": stamp(30)}
                    node = trip
                    *parents, leaf = field.split(".")
                    for parent in parents:
                        node = node.setdefault(parent, {})
                    node[leaf] = [next(iter(values)), raw]
                    key = endpoint.replace("/", "_") + "_" + field.lower().replace(".", "_")
                    parsed = trip_readings(endpoint, {"trips": [trip]})[0]
                    if not isinstance(raw, str) or raw not in values:
                        self.assertNotIn(key, parsed)
                        continue
                    reading = parsed[key]
                    self.assertEqual(reading["value"], values[raw])
                    self.assertEqual(reading["device_class"], device_class)
                    self.assertEqual(reading["domain"], "sensor" if device_class == "enum" else "binary_sensor")
                    self.assertTrue(reading["historical"])
                    self.assertTrue(reading["name"].endswith("(last trip)"))
                    self.assertNotIn("state_class", reading)
                    # Existing Trip event automations still receive the API's text.
                    self.assertEqual(trip_summary(endpoint, trip)[field.lower().replace(".", "_")], raw)
        for endpoint in ("powertrains/data", "speed", "driving/data", "status/data"):
            for reading in trip_readings(endpoint, trip_payload(endpoint))[0].values():
                self.assertNotIn("state_class", reading)

    def test_openings_only_accept_open_and_closed(self):
        for raw in ("open", "closed", "invalid", None, "locked", True, 0, [], {}):
            with self.subTest(raw=raw):
                parsed = readings("status", dict.fromkeys(("hood", "trunk", "sunroof"), raw), "EV")
                for field, device_class in (("hood", "opening"), ("trunk", "opening"), ("sunroof", "window")):
                    key = "status_" + field
                    if raw in ("open", "closed"):
                        self.assertEqual((parsed[key]["domain"], parsed[key]["value"], parsed[key]["device_class"]),
                                         ("binary_sensor", "ON" if raw == "open" else "OFF", device_class))
                        self.assertNotIn("state_class", parsed[key])
                    else:
                        self.assertNotIn(key, parsed)

    def test_enum_values_keep_levels_and_door_lock_information(self):
        cases = [
            ("batteries", lambda v: {"charge": {"status": v}}, "batteries_charge_status",
             {"notCharging": "not_charging", "charging": "charging", "fastCharging": "fast_charging",
              "v2lOperating": "v2l_operating", "v2lStop": "v2l_stop", "v2xOperating": "v2x_operating",
              "reservedCharging": "reserved_charging", "wirelessCharging": "wireless_charging"}),
            ("status", lambda v: {"climateControl": {"mode": v}}, "status_climatecontrol_mode",
             {v: v for v in ("manual", "auto", "off", "error")}),
            ("status", lambda v: {"doors": [{"left": v, "right": v}] * 2}, "status_doors_row2_right",
             {v: v for v in ("open", "closed", "locked")}),
            ("status", lambda v: {"seats": [{side: {"heat": v, "ventilation": v}
                                             for side in ("left", "right")}] * 2}, "status_seats_row2_right_heat",
             {v: v for v in ("off", "low", "middle", "high")}),
        ]
        for endpoint, payload, key, values in cases:
            for raw in (*values, None, "invalid", "unexpected", True, 0, "on"):
                with self.subTest(key=key, raw=raw):
                    parsed = readings(endpoint, payload(raw), "EV")
                    if raw not in values:
                        self.assertNotIn(key, parsed)
                        continue
                    self.assertEqual(parsed[key]["value"], values[raw])
                    for reading in parsed.values():
                        self.assertEqual((reading["domain"], reading["device_class"]), ("sensor", "enum"))
                        self.assertEqual(set(reading["options"]), set(values.values()))
                        self.assertNotIn("state_class", reading)
                        self.assertNotIn("unit_of_measurement", reading)
        self.assertNotIn("device_class", readings("other", {"hood": "closed"}, "EV")["other_hood"])

    def test_all_documented_warnings_and_unknown_codes_keep_the_full_list(self):
        codes = ("lowFuel", "smartKeyBattery", "washFluid", "brakeOil", "engineOil",
                 "tirePressureFrontLeft", "tirePressureFrontRight", "tirePressureRearLeft",
                 "tirePressureRearRight", "tirePressureLow", "frontHeadLamp",
                 "frontLeftTurnSignal", "frontRightTurnSignal", "rearLeftStopLamp",
                 "rearRightStopLamp", "rearLeftTurnSignal", "rearRightTurnSignal")
        for active in (*codes, "futureWarning"):
            parsed = readings("status", {"warnings": [active]}, "EV")
            self.assertEqual(len(parsed), 18)
            self.assertEqual(parsed["status_warnings"]["attributes"]["warnings"], [active])
            for code in codes:
                reading = parsed["status_warning_" + code.lower()]
                self.assertEqual((reading["domain"], reading["device_class"], reading["value"]),
                                 ("binary_sensor", "problem", "ON" if code == active else "OFF"))
        cleared = readings("status", {"warnings": []}, "EV")
        self.assertTrue(all(r["value"] == "OFF" for key, r in cleared.items() if key != "status_warnings"))
        for value in (None, "invalid", "", "lowFuel", False, {}, {"lowFuel": True},
                      ["lowFuel", None], ["lowFuel", 1], ["invalid"], ["lowFuel", ""]):
            with self.subTest(value=value):
                self.assertEqual(readings("status", {"warnings": value}, "EV"), {})
        self.assertEqual(readings("status", {}, "EV"), {})

    def test_charge_targets_are_percentages_not_battery_levels(self):
        parsed = readings("batteries", {"charge": {"stateOfCharge": 42,
                          "targetStateOfCharge": {"standard": 80, "quick": 100}}}, "EV")
        self.assertEqual([key for key, r in parsed.items() if r.get("device_class") == "battery"],
                         ["batteries_charge_stateofcharge"])
        for kind, value in (("standard", 80), ("quick", 100)):
            reading = parsed["batteries_charge_targetstateofcharge_" + kind]
            self.assertEqual((reading["value"], reading["unit_of_measurement"]), (value, "%"))
            self.assertNotIn("state_class", reading)
        traction = readings("powertrains", {"batteries": [{"type": "main", "remainRatio": 43}]}, "EV")
        self.assertEqual(traction["powertrains_batteries_main_remainratio"]["device_class"], "battery")

    def test_all_enum_states_have_valid_translation_keys_and_labels(self):
        component = Path(__file__).parents[1] / "custom_components/pleos_vehicle_data"
        for filename in ("strings.json", "translations/en.json"):
            translations = json.loads((component / filename).read_text())["entity"]["sensor"]
            for key, options in (ENUM_OPTIONS | TRIP_ENUM_OPTIONS).items():
                self.assertEqual(set(translations[key]["state"]), set(options))
                for state in options:
                    self.assertRegex(state, r"^[a-z0-9_]+$")
                    self.assertTrue(translations[key]["state"][state])


class NativeEntityTests(HomeAssistantTestCase):
    async def test_every_documented_sensor_registers_with_home_assistant(self):
        await entity_registry.async_load(self.hass, load_empty=True)
        payloads = {endpoint: payload | {"timestamp": stamp()} for endpoint, payload in SNAPSHOTS.items()}
        payloads |= {endpoint: trip_payload(endpoint) for endpoint in ("powertrains/data", "speed", "driving/data", "status/data")}
        self.client.vehicles = AsyncMock(return_value=[CAR])
        self.client.get = AsyncMock(side_effect=lambda path: payloads.get(path.split("/", 4)[-1].split("?", 1)[0]))
        await self.coordinator.async_refresh()
        car_id = vehicle_id("kia", CAR["vin"])
        platforms = []
        try:
            for domain, factory in (("sensor", ReadingSensor), ("binary_sensor", ReadingBinarySensor)):
                platform = EntityPlatform(hass=self.hass, logger=logging.getLogger(__name__), domain=domain,
                                          platform_name=DOMAIN, platform=None, scan_interval=timedelta(minutes=15),
                                          entity_namespace=None)
                platform.config_entry = self.entry
                platforms.append(platform)
                entities = [factory(self.coordinator, car_id, key, spec)
                            for key, spec in self.coordinator.data["cars"][car_id]["readings"].items()
                            if spec["domain"] == domain]
                await platform.async_add_entities(entities)
                for entity in entities:
                    state = self.hass.states.get(entity.entity_id)
                    self.assertIsNotNone(state, entity.key)
                    self.assertNotIn(state.state, ("unknown", "unavailable"), entity.key)
            self.assertGreater(len(self.hass.states.async_all()), 100)
        finally:
            for platform in platforms:
                await platform.async_reset()

    async def test_upgrade_ids_metadata_states_and_warning_failure_recovery(self):
        await entity_registry.async_load(self.hass, load_empty=True)
        registry = entity_registry.async_get(self.hass)
        car_id = vehicle_id("kia", CAR["vin"])
        old_bonnet = registry.async_get_or_create(
            "sensor", DOMAIN, car_id + "_status_hood", config_entry=self.entry, suggested_object_id="custom_bonnet")
        old_charge = registry.async_get_or_create(
            "sensor", DOMAIN, car_id + "_batteries_charge_status", config_entry=self.entry,
            suggested_object_id="custom_charging_status")
        old_limit = registry.async_get_or_create(
            "sensor", DOMAIN, car_id + "_batteries_charge_targetstateofcharge_quick", config_entry=self.entry,
            suggested_object_id="custom_dc_limit", original_device_class="battery")
        payloads = {
            "status": {"timestamp": stamp(), "hood": "open", "warnings": ["washFluid"]},
            "batteries": {"timestamp": stamp(), "charge": {"status": "fastCharging", "stateOfCharge": 42,
                          "targetStateOfCharge": {"standard": 100, "quick": 100}}},
        }
        self.client.vehicles = AsyncMock(return_value=[CAR | {"nickname": "Van"}])
        self.client.get = AsyncMock(side_effect=lambda path: payloads.get(path.rsplit("/", 1)[-1]))
        await self.coordinator.async_refresh()
        platforms = []
        try:
            for domain, factory in (("sensor", ReadingSensor), ("binary_sensor", ReadingBinarySensor)):
                platform = EntityPlatform(hass=self.hass, logger=logging.getLogger(__name__), domain=domain,
                                          platform_name=DOMAIN, platform=None, scan_interval=timedelta(minutes=15),
                                          entity_namespace=None)
                platform.config_entry = self.entry
                platforms.append(platform)
                await platform.async_add_entities([
                    factory(self.coordinator, car_id, key, spec)
                    for key, spec in self.coordinator.data["cars"][car_id]["readings"].items()
                    if spec["domain"] == domain and key in (
                        "status_hood", "status_warning_washfluid", "batteries_charge_status",
                        "batteries_charge_stateofcharge", "batteries_charge_targetstateofcharge_standard",
                        "batteries_charge_targetstateofcharge_quick")])
            self.assertEqual(registry.async_get(old_bonnet.entity_id), old_bonnet)
            self.assertEqual(self.hass.states.get("binary_sensor.van_bonnet").state, "on")
            self.assertEqual(self.hass.states.get(old_charge.entity_id).state, "fast_charging")
            limit = self.hass.states.get(old_limit.entity_id)
            self.assertEqual(limit.state, "100")
            self.assertNotIn("device_class", limit.attributes)
            self.assertIsNone(registry.async_get(old_limit.entity_id).original_device_class)
            batteries = [state for state in self.hass.states.async_all("sensor")
                         if state.attributes.get("device_class") == "battery"]
            self.assertEqual([(s.entity_id, s.state) for s in batteries], [("sensor.van_battery_level", "42")])
            warning_id = "binary_sensor.van_washer_fluid_warning"
            self.assertEqual(self.hass.states.get(warning_id).attributes["device_class"], "problem")
            for warnings, expected in (([], "off"), (None, "unavailable"), (["invalid"], "unavailable"),
                                       (["washFluid"], "on")):
                payloads["status"]["warnings"] = warnings
                payloads["status"]["hood"] = "closed"
                await self.coordinator.async_refresh()
                self.assertEqual(self.hass.states.get(warning_id).state, expected)
                self.assertEqual(self.hass.states.get("binary_sensor.van_bonnet").state, "off")
            self.client.get = AsyncMock(side_effect=ApiError(503, "fixture_failure"))
            await self.coordinator.async_refresh()
            self.assertEqual(self.hass.states.get(warning_id).state, "unavailable")
            self.assertEqual(self.hass.states.get("binary_sensor.van_bonnet").state, "unavailable")
            self.assertEqual(self.hass.states.get(old_charge.entity_id).state, "unavailable")
            self.assertEqual(self.hass.states.get(old_limit.entity_id).state, "100")
            self.assertTrue(self.hass.states.get(old_limit.entity_id).attributes["last_known"])
            self.client.get = AsyncMock(side_effect=lambda path: payloads.get(path.rsplit("/", 1)[-1]))
            await self.coordinator.async_refresh()
            self.assertEqual(self.hass.states.get(warning_id).state, "on")
        finally:
            for platform in platforms:
                await platform.async_reset()
