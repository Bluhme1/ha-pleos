"""API units pass through to Home Assistant's distance conversion."""

import logging
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.pleos_vehicle_data.const import DOMAIN
from custom_components.pleos_vehicle_data.data import readings, vehicle_id
from custom_components.pleos_vehicle_data.sensor import ReadingSensor

from support import CAR, HomeAssistantTestCase, stamp


class OdometerUnitTests(HomeAssistantTestCase):
    async def start_odometer(self, value, unit, system):
        self.hass.config.units = system
        await entity_registry.async_load(self.hass, load_empty=True)
        await self.populate({"timestamp": stamp(), "odometer": {"value": value, "unit": unit}})
        self.car_id = vehicle_id("kia", CAR["vin"])
        spec = self.coordinator.data["cars"][self.car_id]["readings"]["driving_odometer"]
        sensor = ReadingSensor(self.coordinator, self.car_id, "driving_odometer", spec)
        platform = EntityPlatform(hass=self.hass, logger=logging.getLogger(__name__), domain="sensor",
                                  platform_name=DOMAIN, platform=None, scan_interval=timedelta(minutes=15),
                                  entity_namespace=None)
        platform.config_entry = self.entry
        await platform.async_add_entities([sensor])
        self.addAsyncCleanup(platform.async_reset)
        return sensor

    async def test_all_documented_odometer_units_convert_to_miles(self):
        sensor = await self.start_odometer(1609.344, "km", US_CUSTOMARY_SYSTEM)
        for raw_unit, native_unit, value in (("km", "km", 1609.344), ("mile", "mi", 1000),
                                             ("meter", "m", 1609344), ("feet", "ft", 5280000)):
            with self.subTest(unit=raw_unit):
                reading = readings("driving", {"odometer": {"value": value, "unit": raw_unit}}, "EV")["driving_odometer"]
                self.coordinator.data["cars"][self.car_id]["readings"]["driving_odometer"] = reading
                sensor.async_write_ha_state()
                state = self.hass.states.get(sensor.entity_id)
                self.assertEqual((sensor.native_value, sensor.native_unit_of_measurement), (value, native_unit))
                self.assertEqual(state.attributes["unit_of_measurement"], "mi")
                self.assertAlmostEqual(float(state.state), 1000, places=3)

    async def test_api_miles_convert_to_metric_distance(self):
        sensor = await self.start_odometer(1000, "mile", METRIC_SYSTEM)
        state = self.hass.states.get(sensor.entity_id)
        self.assertEqual(state.attributes["unit_of_measurement"], "km")
        self.assertAlmostEqual(float(state.state), 1609.344, places=3)

    async def test_entity_unit_preference_converts_value_as_well_as_label(self):
        sensor = await self.start_odometer(1609.344, "km", METRIC_SYSTEM)
        entity_registry.async_get(self.hass).async_update_entity_options(
            sensor.entity_id, "sensor", {"unit_of_measurement": "mi"})
        await self.hass.async_block_till_done()
        state = self.hass.states.get(sensor.entity_id)
        self.assertEqual(state.attributes["unit_of_measurement"], "mi")
        self.assertAlmostEqual(float(state.state), 1000, places=3)

    async def test_correct_mislabelled_odometer_before_display_conversion(self):
        self.coordinator.options["odometer_km_vehicles"] = [vehicle_id("kia", CAR["vin"])]
        sensor = await self.start_odometer(5177.5, "mile", US_CUSTOMARY_SYSTEM)
        state = self.hass.states.get(sensor.entity_id)
        self.assertEqual(state.attributes["unit_of_measurement"], "mi")
        self.assertAlmostEqual(float(state.state), 3217.149, places=3)
        self.assertEqual((sensor.native_value, sensor.native_unit_of_measurement), (5177.5, "km"))
        self.assertEqual(state.attributes["api_unit_of_measurement"], "mi")
        raw = self.coordinator.data["cars"][self.car_id]["readings"]["driving_api"]["attributes"]["data"]
        self.assertEqual(raw["odometer"], {"value": 5177.5, "unit": "mile"})

        entity_registry.async_get(self.hass).async_update_entity_options(
            sensor.entity_id, "sensor", {"unit_of_measurement": "km"})
        await self.hass.async_block_till_done()
        self.assertEqual(float(self.hass.states.get(sensor.entity_id).state), 5177.5)

    async def test_correction_is_limited_to_selected_car_and_snapshot_odometer(self):
        selected = vehicle_id("kia", CAR["vin"])
        other = CAR | {"vin": "SYNTHETIC-CAR-002"}
        other_id = vehicle_id("kia", other["vin"])
        self.coordinator.options["odometer_km_vehicles"] = [selected]
        self.client.vehicles = AsyncMock(return_value=[CAR, other])
        trip = {"triggerStartTime": stamp(30), "tripLength": 60000, "odometer": {"value": [5170, 5177.5]}}
        self.client.get = AsyncMock(side_effect=lambda path: {"trips": [trip]} if "/driving/data?" in path
                                   else {"timestamp": stamp(), "odometer": {"value": 5177.5, "unit": "mile"}})
        cars = (await self.coordinator._async_update_data())["cars"]
        self.assertEqual(cars[selected]["readings"]["driving_odometer"]["unit_of_measurement"], "km")
        self.assertEqual(cars[other_id]["readings"]["driving_odometer"]["unit_of_measurement"], "mi")
        for car in cars.values():
            distance = car["readings"]["driving_data_trip_distance"]
            self.assertEqual((distance["value"], distance["unit_of_measurement"]), (7.5, "km"))

    async def test_correction_keeps_other_units_and_rejects_invalid_values(self):
        car_id = vehicle_id("kia", CAR["vin"])
        self.coordinator.options["odometer_km_vehicles"] = [car_id]
        for raw_unit, expected in (("km", "km"), ("meter", "m"), ("feet", "ft")):
            with self.subTest(unit=raw_unit):
                await self.populate({"odometer": {"value": 5177.5, "unit": raw_unit}})
                reading = self.coordinator.data["cars"][car_id]["readings"]["driving_odometer"]
                self.assertEqual((reading["value"], reading["unit_of_measurement"]), (5177.5, expected))
                self.assertNotIn("api_unit_of_measurement", reading.get("attributes", {}))
        for invalid in (None, True, -1, float("inf"), "5177.5"):
            with self.subTest(value=invalid):
                await self.populate({"odometer": {"value": invalid, "unit": "mile"}})
                self.assertNotIn("driving_odometer", self.coordinator.data["cars"][car_id]["readings"])
