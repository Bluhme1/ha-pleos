"""Trip sample parsing, aggregates and new-trip detection, without Home Assistant."""

import unittest

from custom_components.pleos_vehicle_data.data import (new_trips, prune_seen, trip_readings)

from support import stamp


class TripReadingTests(unittest.TestCase):
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


class TripAggregateTests(unittest.TestCase):
    def trip(self, **fields):
        return {"trips": [{"triggerStartTime": stamp(60), "tripLength": 60000, **fields}]}

    def test_numeric_fields_get_min_max_mean_of_valid_samples(self):
        data = self.trip(engine={"rpm": [800, "invalid", None, 99999, 3000, 1600], "oilTemperature": [80]})
        attrs = trip_readings("powertrains/data", data)[0]["powertrains_data_engine_rpm"]["attributes"]
        self.assertEqual((attrs["trip_min"], attrs["trip_max"], attrs["trip_mean"]), (800, 3000, 1800))
        self.assertEqual((attrs["valid_samples"], attrs["total_samples"]), (3, 6))
        oil = trip_readings("powertrains/data", data)[0]["powertrains_data_engine_oiltemperature"]["attributes"]
        self.assertEqual((oil["trip_min"], oil["trip_max"], oil["valid_samples"]), (80, 80, 1))

    def test_aggregates_use_converted_values_in_the_last_samples_unit(self):
        data = self.trip(tire={"pressureFrontLeft": [70, 72, 36], "pressureUnit": ["kpa", "kpa", "psi"]},
                         location={"speed": [50, 100, 30, 60], "speedUnit": ["kph", "mph", "kph", "kph"]})
        tyre = trip_readings("status/data", data)[0]["status_data_tire_pressurefrontleft"]
        self.assertEqual(tyre["value"], 36)
        self.assertEqual((tyre["attributes"]["trip_min"], tyre["attributes"]["valid_samples"]), (36, 1))
        speed = trip_readings("speed", data)[0]["speed_location_speed"]["attributes"]
        self.assertEqual((speed["trip_min"], speed["trip_max"], speed["trip_mean"], speed["valid_samples"]),
                         (30, 60, 46.667, 3))
        kpa = trip_readings("status/data", self.trip(tire={"pressureRearLeft": [70, 72], "pressureUnit": ["kpa", "kpa"]}))[0]
        self.assertEqual(kpa["status_data_tire_pressurerearleft"]["attributes"]["trip_max"], 360)

    def test_text_fields_have_no_aggregates(self):
        data = self.trip(transmission={"gear": ["P", "D"]})
        self.assertNotIn("trip_min", trip_readings("driving/data", data)[0]["driving_data_transmission_gear"]["attributes"])

    def test_trip_distance_from_first_and_last_valid_odometer_samples(self):
        data = self.trip(odometer={"value": ["invalid", 1200.5, 1203.0, None, 1212.8, "invalid"]})
        result = trip_readings("driving/data", data)[0]
        distance = result["driving_data_trip_distance"]
        self.assertEqual((distance["value"], distance["unit_of_measurement"]), (12.3, "km"))
        self.assertEqual((distance["attributes"]["odometer_start"], distance["attributes"]["odometer_end"]), (1200.5, 1212.8))
        self.assertTrue(distance["historical"])
        self.assertNotIn("driving_data_odometer_value", result)
        for odometer in ([1200], [1210, 1200], []):
            self.assertNotIn("driving_data_trip_distance", trip_readings("driving/data", self.trip(odometer={"value": odometer}))[0])


class TripEventDataTests(unittest.TestCase):
    def test_new_trips_skips_seen_invalid_and_duplicate_starts_in_order(self):
        older, newer = stamp(300), stamp(60)
        data = {"trips": [{"triggerStartTime": newer, "tripLength": 1}, {"triggerStartTime": older},
                          {"triggerStartTime": newer, "tripLength": 2}, {"triggerStartTime": "not-a-time"},
                          {"triggerStartTime": "2026-01-01T00:00:00"}, "junk", {"tripLength": 3}]}
        self.assertEqual([trip["triggerStartTime"] for trip in new_trips(data, set())], [older, newer])
        self.assertEqual(new_trips(data, set())[1]["tripLength"], 1)
        self.assertEqual([trip["triggerStartTime"] for trip in new_trips(data, {older})], [newer])
        self.assertEqual(new_trips(None, set()), [])
        self.assertEqual(new_trips({"trips": "invalid"}, set()), [])

    def test_prune_seen_keeps_recent_starts_only(self):
        recent, old = stamp(60), stamp(60 * 24 * 5)
        self.assertEqual(prune_seen([recent, old, "bad"], 4 * 86400), [recent])


if __name__ == "__main__":
    unittest.main()
