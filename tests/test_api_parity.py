"""Synthetic examples covering the ten documented common API response schemas."""

import unittest

from custom_components.pleos_vehicle_data.data import WARNING_NAMES, location, readings, trip_readings


class ApiParityTests(unittest.TestCase):
    def test_oversized_json_numbers_do_not_crash_normalization(self):
        huge = 10 ** 400
        self.assertEqual(readings("status", {"unknownField": huge, "hood": "closed"}, "EV")["status_hood"]["value"], "OFF")
        self.assertNotIn("status_unknownfield", readings("status", {"unknownField": huge}, "EV"))
        self.assertIsNone(location({"timestamp": "2026-01-01T00:00:00Z", "location": {"type": 0, "latitude": huge, "longitude": 0}}))
        actual, _ = trip_readings("powertrains/data", {"trips": [{"triggerStartTime": "2026-01-01T00:00:00Z", "tripLength": huge, "engine": {"rpm": [huge]}}]})
        self.assertEqual(set(actual), {"powertrains_data_trip_start"})

    def test_documented_snapshot_fields(self):
        # https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/
        cases = {
            "batteries": ({"charge": {
                "plugin": "connected", "status": "v2lOperating", "charging": False,
                "stateOfCharge": 40, "batteryCapacity": 100000,
                "targetStateOfCharge": {"standard": 80, "quick": 90}, "remainTime": 10,
            }}, {
                "charge_plugin": "ON", "charge_status": "v2l_operating", "charge_charging": "OFF",
                "charge_stateofcharge": 40, "charge_batterycapacity": 100000 / 3600,
                "charge_targetstateofcharge_standard": 80, "charge_targetstateofcharge_quick": 90,
                "charge_remaintime": 10,
            }),
            "powertrains": ({
                "engine": {"fuelLevel": 30}, "batteries": [{"type": "main", "remainRatio": 50}],
                "distanceToEmpties": [{"type": kind, "value": "100", "unit": "km"}
                                      for kind in ("ICE", "EV", "HEV", "PHEV", "FCEV")],
            }, {"engine_fuellevel": 30, "batteries_main_remainratio": 50,
                "distancetoempties_ice": 100, "distancetoempties_ev": 100,
                "distancetoempties_hev": 100, "distancetoempties_phev": 100,
                "distancetoempties_fcev": 100}),
            "driving": ({
                "ignition": {"status": "off", "ignitionDetails": [
                    {"type": "ign1", "status": "off"}, {"type": "ign3", "status": "on"},
                    {"type": "acc", "status": "off"}]},
                "sleepMode": "on", "odometer": {"value": 1000, "unit": "mile"},
                "transmission": {"parkingPosition": True},
            }, {"ignition_status": "OFF", "ignition_ignitiondetails_ign1_status": "OFF",
                "ignition_ignitiondetails_ign3_status": "ON", "ignition_ignitiondetails_acc_status": "OFF",
                "sleepmode": "ON", "odometer": 1000, "transmission_parkingposition": "ON"}),
            "status": ({
                "doors": [{"left": "locked", "right": "closed"}, {"left": "open", "right": "locked"}],
                "hood": "closed", "trunk": "open", "sunroof": "closed",
                "tire": [{"left": 72, "right": 70, "unit": "kpa"}, {"left": 36, "right": 35, "unit": "bar"}],
                "warnings": ["washFluid", "lowFuel"],
                "climateControl": {"mode": "auto", "status": "on", "speed": -1,
                                   "temperature": {"value": 70, "unit": "F"}},
                "windshield": {"defrost": "off"}, "steeringWheelHeat": "on",
                "seats": [{"left": {"heat": "low", "ventilation": "off"},
                           "right": {"heat": "off", "ventilation": "high"}},
                          {"left": {"heat": "middle", "ventilation": "off"},
                           "right": {"heat": "high", "ventilation": "off"}}],
                "outsideTemperature": {"value": 15, "unit": "C"},
            }, {"doors_row1_left": "locked", "doors_row1_right": "closed",
                "doors_row2_left": "open", "doors_row2_right": "locked",
                "hood": "OFF", "trunk": "ON", "sunroof": "OFF",
                "tire_row1_left": 360, "tire_row1_right": 350, "tire_row2_left": 3.6, "tire_row2_right": 3.5,
                "warnings": "washFluid, lowFuel", "climatecontrol_mode": "auto", "climatecontrol_status": "ON",
                "climatecontrol_speed": "auto", "climatecontrol_temperature": 70, "windshield_defrost": "OFF",
                "steeringwheelheat": "ON", "seats_row1_left_heat": "low", "seats_row1_left_ventilation": "off",
                "seats_row1_right_heat": "off", "seats_row1_right_ventilation": "high",
                "seats_row2_left_heat": "middle", "seats_row2_left_ventilation": "off",
                "seats_row2_right_heat": "high", "seats_row2_right_ventilation": "off", "outsidetemperature": 15}),
            "locations": ({"location": {"latitude": 0, "longitude": 0, "altitude": 20, "heading": 90,
                                         "speed": {"value": 12, "unit": "mps"}, "type": 0}},
                          {"location_latitude": 0, "location_longitude": 0, "location_altitude": 20,
                           "location_heading": 90, "location_speed": 12, "location_type": "WGS84"}),
            "freezer": ({"freezer": {"status": "on", "temperature": -20}},
                        {"freezer_status": "ON", "freezer_temperature": -20}),
        }
        for endpoint, (payload, expected) in cases.items():
            with self.subTest(endpoint=endpoint):
                if endpoint == "status":
                    expected |= {"warning_" + code.lower(): "ON" if code in payload["warnings"] else "OFF"
                                 for code in WARNING_NAMES}
                actual = readings(endpoint, payload | {"timestamp": "2026-01-01T00:00:00Z"}, "HV")
                self.assertEqual({key: value["value"] for key, value in actual.items()},
                                 {endpoint + "_" + key: value for key, value in expected.items()})
        self.assertEqual(readings("driving", cases["driving"][0], "HV")["driving_odometer"]["unit_of_measurement"], "mi")
        self.assertEqual(readings("status", cases["status"][0], "HV")["status_climatecontrol_temperature"]["unit_of_measurement"], "°F")

    def test_all_documented_trip_sample_fields(self):
        cases = {
            "powertrains/data": ({"batteries": {"hv": {"voltage": [300]}},
                                  "engine": {"oilTemperature": [30], "rpm": [900]}},
                                 {"batteries_hv_voltage": 300, "engine_oiltemperature": 30, "engine_rpm": 900}),
            "speed": ({"location": {"speed": [20], "speedUnit": ["mph"]},
                       "wheel": {"speedFrontLeft": [30], "speedFrontRight": [31],
                                 "speedRearLeft": [32], "speedRearRight": [33]}},
                      {"location_speed": 20, "location_speedunit": "mph", "wheel_speedfrontleft": 30,
                       "wheel_speedfrontright": 31, "wheel_speedrearleft": 32, "wheel_speedrearright": 33}),
            "driving/data": ({
                "ignition": {"status": ["on"]}, "odometer": {"value": [100]},
                "acceleration": {"longitudinal": [-1]}, "angularVelocity": {"yaw": [2]},
                "isla": {"optionUsm": ["assist"], "optionUsm2": ["information"]},
                "seatbelt": {"assistance": ["unbelted"], "driver": ["belted"]},
                "steeringWheel": {"angle": [-10], "rotationSpeed": [3]}, "transmission": {"gear": ["d"]},
            }, {"ignition_status": "ON", "odometer_value": 100, "acceleration_longitudinal": -1,
                "angularvelocity_yaw": 2, "isla_optionusm": "assist", "isla_optionusm2": "information",
                "seatbelt_assistance": "unbelted", "seatbelt_driver": "belted", "steeringwheel_angle": -10,
                "steeringwheel_rotationspeed": 3, "transmission_gear": "d"}),
            "status/data": ({
                "doors": {"openAssistance": ["close"], "openDriver": ["open"],
                          "openRearLeft": ["close"], "openRearRight": ["open"]},
                "lamp": {"setting": ["autoLightSwOn"]},
                "tire": {"pressureFrontLeft": [30], "pressureFrontRight": [31],
                         "pressureRearLeft": [32], "pressureRearRight": [33], "pressureUnit": ["bar"]},
                "warnings": {"lowFuelLevel": ["off"]}, "outsideTemperature": {"value": [0]},
            }, {"doors_openassistance": "OFF", "doors_opendriver": "ON", "doors_openrearleft": "OFF",
                "doors_openrearright": "ON", "lamp_setting": "auto",
                "tire_pressurefrontleft": 3, "tire_pressurefrontright": 3.1, "tire_pressurerearleft": 3.2,
                "tire_pressurerearright": 3.3, "tire_pressureunit": "bar", "warnings_lowfuellevel": "OFF",
                "outsidetemperature_value": 0}),
        }
        for endpoint, (payload, expected) in cases.items():
            with self.subTest(endpoint=endpoint):
                start = "2026-01-01T00:00:00Z"
                actual, timestamp = trip_readings(endpoint, {"trips": [payload | {"triggerStartTime": start, "tripLength": 1000}]})
                prefix = endpoint.replace("/", "_") + "_"
                self.assertEqual(timestamp, start)
                self.assertEqual({key: value["value"] for key, value in actual.items()},
                                 {prefix + key: value for key, value in expected.items()} |
                                 {prefix + "trip_start": start, prefix + "trip_duration": 1})

    def test_documented_snapshot_ranges_and_units(self):
        invalid = [
            ("driving", {"odometer": {"value": -1, "unit": "km"}}),
            ("driving", {"odometer": {"value": 16777215, "unit": "km"}}),
            ("driving", {"odometer": {"value": True, "unit": "km"}}),
            ("driving", {"odometer": {"value": 100, "unit": "kph"}}),
            ("status", {"climateControl": {"speed": 9}}),
            ("status", {"climateControl": {"speed": 1.5}}),
            ("status", {"climateControl": {"temperature": {"value": 101, "unit": "C"}}}),
            ("status", {"outsideTemperature": {"value": -101, "unit": "F"}}),
            ("status", {"outsideTemperature": {"value": 20, "unit": "km"}}),
            ("status", {"tire": [{"left": 254.5, "unit": "psi"}]}),
            ("locations", {"location": {"speed": {"value": 1, "unit": "km"}}}),
            ("powertrains", {"distanceToEmpties": [{"type": "invalid", "value": "100", "unit": "km"}]}),
            ("powertrains", {"distanceToEmpties": [{"type": "EV", "value": "100", "unit": "kph"}]}),
            ("powertrains", {"distanceToEmpties": [{"type": "EV", "value": True, "unit": "km"}]}),
        ]
        for endpoint, payload in invalid:
            with self.subTest(endpoint=endpoint, payload=payload):
                self.assertEqual(readings(endpoint, payload, "EV"), {})
        self.assertEqual(readings("driving", {"odometer": {"value": 16777214, "unit": "km"}}, "EV")["driving_odometer"]["value"], 16777214)

    def test_malformed_units_do_not_break_other_readings(self):
        for unit in ([], {}, 42, True):
            with self.subTest(unit=unit):
                actual = readings("status", {"hood": "closed", "outsideTemperature": {"value": 20, "unit": unit}}, "EV")
                self.assertEqual(list(actual), ["status_hood"])
        self.assertEqual(readings("powertrains", {"distanceToEmpties": [{"type": [], "value": 100, "unit": "km"}]}, "EV"), {})

    def test_coordinate_system_is_exposed_without_misplacing_non_wgs84_cars(self):
        for code, name in enumerate(("WGS84", "Bessel", "CoordShift")):
            payload = {"location": {"type": code, "latitude": 0, "longitude": 0}, "timestamp": "2026-01-01T00:00:00Z"}
            reading = readings("locations", payload, "EV")["locations_location_type"]
            self.assertEqual(reading["value"], name)
            self.assertEqual(reading["device_class"], "enum")
            self.assertEqual(location(payload) is not None, code == 0)
        for value in (True, 0.0, 3, -1, "0"):
            payload = {"location": {"type": value}, "timestamp": "2026-01-01T00:00:00Z"}
            self.assertEqual(readings("locations", payload, "EV"), {})
            self.assertIsNone(location(payload))

    def test_oversized_strings_remain_outside_entity_states(self):
        self.assertEqual(readings("status", {"unknownField": "x" * 256}, "EV"), {})
        actual, _ = trip_readings("driving/data", {"trips": [{"triggerStartTime": "2026-01-01T00:00:00Z",
                                                            "ignition": {"status": ["x" * 256]}}]})
        self.assertNotIn("driving_data_ignition_status", actual)
