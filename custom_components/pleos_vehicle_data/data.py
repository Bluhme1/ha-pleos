"""Normalize documented vehicle fields without inventing missing readings."""

import hashlib
import math
import re
from datetime import datetime, timezone

from .const import ENDPOINT_NAMES

UNITS = {"C": "°C", "F": "°F", "km": "km", "mile": "mi", "miles": "mi",
         "meter": "m", "feet": "ft", "psi": "psi", "kpa": "kPa", "bar": "bar",
         "kph": "km/h", "mph": "mph", "mps": "m/s"}


NAMES = {"batteries_charge_stateofcharge": "Battery level", "batteries_charge_charging": "Charging",
         "batteries_charge_plugin": "Plugged in", "batteries_charge_remaintime": "Charge time remaining",
         "batteries_charge_status": "Charging status", "batteries_charge_batterycapacity": "Battery capacity",
         "batteries_charge_targetstateofcharge_standard": "AC charge limit",
         "batteries_charge_targetstateofcharge_quick": "DC charge limit",
         "powertrains_engine_fuellevel": "Fuel level", "powertrains_batteries_main_remainratio": "Traction battery level",
         "powertrains_distancetoempties_ev": "EV range", "driving_odometer": "Odometer",
         "powertrains_distancetoempties_ice": "Fuel range", "powertrains_distancetoempties_hev": "Hybrid range",
         "powertrains_distancetoempties_phev": "Plug-in hybrid range", "powertrains_distancetoempties_fcev": "Hydrogen range",
         "driving_ignition_status": "Ignition", "driving_sleepmode": "Sleep mode",
         "driving_ignition_ignitiondetails_ign1_status": "Ignition power",
         "driving_ignition_ignitiondetails_ign3_status": "High-voltage system power",
         "driving_ignition_ignitiondetails_acc_status": "Accessory power",
         "driving_transmission_parkingposition": "In park",
         "status_hood": "Bonnet", "status_trunk": "Boot", "status_sunroof": "Sunroof",
         "status_warnings": "Warnings", "status_climatecontrol_mode": "Climate mode",
         "status_climatecontrol_status": "Climate control", "status_climatecontrol_speed": "Cabin fan speed",
         "status_climatecontrol_temperature": "Cabin target temperature",
         "status_outsidetemperature": "Outside temperature", "status_windshield_defrost": "Windscreen defrost",
         "status_steeringwheelheat": "Steering wheel heating",
         "freezer_freezer_status": "Freezer", "freezer_freezer_temperature": "Freezer temperature",
         "locations_location_latitude": "Latitude", "locations_location_longitude": "Longitude",
         "locations_location_altitude": "Altitude", "locations_location_heading": "Heading",
         "locations_location_speed": "Speed",
         "locations_location_type": "Coordinate system",
         "status_tire_row1_left": "Front left tyre pressure", "status_tire_row1_right": "Front right tyre pressure",
         "status_tire_row2_left": "Rear left tyre pressure", "status_tire_row2_right": "Rear right tyre pressure",
         **{f"status_doors_row{row}_{side}": f"{position} {side} door"
            for row, position in ((1, "Front"), (2, "Rear")) for side in ("left", "right")},
         **{f"status_seats_row{row}_{side}_{field}": f"{position} {side} seat {name}"
            for row, position in ((1, "Front"), (2, "Rear")) for side in ("left", "right")
            for field, name in (("heat", "heating"), ("ventilation", "ventilation"))}}

TRIP_NAMES = {
    "batteries.hv.voltage": "Traction battery voltage", "engine.oilTemperature": "Engine oil temperature",
    "engine.rpm": "Engine speed", "location.speed": "Speed", "location.speedUnit": "Speed unit",
    "ignition.status": "Ignition", "odometer.value": "Odometer", "acceleration.longitudinal": "Forward acceleration",
    "angularVelocity.yaw": "Turning rate", "isla.optionUsm": "Speed limit assist setting",
    "isla.optionUsm2": "Speed limit assist secondary setting", "seatbelt.assistance": "Passenger seat belt",
    "seatbelt.driver": "Driver seat belt", "steeringWheel.angle": "Steering wheel angle",
    "steeringWheel.rotationSpeed": "Steering wheel turning speed", "transmission.gear": "Gear",
    "lamp.setting": "Exterior light setting", "tire.pressureUnit": "Tyre pressure unit",
    "warnings.lowFuelLevel": "Low fuel warning", "outsideTemperature.value": "Outside temperature",
    "doors.openAssistance": "Front passenger door", "doors.openDriver": "Driver door",
    "doors.openRearLeft": "Rear left door", "doors.openRearRight": "Rear right door",
    **{f"{group}.{field}{part}": f"{name} {side} {suffix}"
       for part, name, side in (("FrontLeft", "Front", "left"), ("FrontRight", "Front", "right"),
                                ("RearLeft", "Rear", "left"), ("RearRight", "Rear", "right"))
       for group, field, suffix in (("wheel", "speed", "wheel speed"), ("tire", "pressure", "tyre pressure"))},
}


def identifier(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def label(path):
    return " ".join(re.sub(r"([a-z])([A-Z])", r"\1 \2", str(part)).replace("_", " ") for part in path).capitalize()


def reported_age(timestamp):
    try:
        stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        return max(0, age) if age >= -300 else None
    except (TypeError, ValueError, AttributeError):
        return None


def finite_number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def readings(endpoint, data, vehicle_type):
    """Keep unknown fields as plain sensors; apply only documented semantics."""
    result = {}
    if not isinstance(data, dict):
        return result

    def walk(value, path=(), unit=None):
        if isinstance(value, dict):
            local_unit = value.get("unit", unit)
            if local_unit == "invalid" or (local_unit is not None and not isinstance(local_unit, str)):
                return
            for key, child in value.items():
                if key not in ("unit", "type", "timestamp") or (endpoint == "locations" and path == ("location",) and key == "type"):
                    walk(child, path if key == "value" else (*path, key), local_unit)
            return
        if isinstance(value, list):
            if path == ("warnings",):
                if all(isinstance(item, str) for item in value):
                    walk(", ".join(value)[:255] or "None", path)
                return
            for index, child in enumerate(value):
                part = child.get("type") if isinstance(child, dict) else None
                if part == "invalid" or (part is not None and not isinstance(part, str)):
                    continue
                walk(child, (*path, part or f"row{index + 1}"), unit)
            return
        if value is None or value == "invalid" or not path:
            return
        if not isinstance(value, (str, int, float, bool)):
            return
        if isinstance(value, str) and len(value) > 255:
            return
        if endpoint == "powertrains" and path == ("engine", "fuelLevel") and vehicle_type in ("EV", "FV"):
            return
        opts = {}
        domain = "sensor"
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if numeric:
            if not finite_number(value):
                return
            opts["state_class"] = "measurement"
        if endpoint == "status" and path[0] == "tire":
            if not numeric or not 0 <= value <= 254 or unit not in ("psi", "kpa", "bar"):
                return
            value = value * 5 if unit == "kpa" else value / 10 if unit == "bar" else value
            opts["device_class"] = "pressure"
        if unit in UNITS and numeric:
            opts["unit_of_measurement"] = UNITS[unit]
            if unit in ("C", "F"):
                opts["device_class"] = "temperature"
        if path[-1] in ("stateOfCharge", "remainRatio", "fuelLevel") or path[:2] == ("charge", "targetStateOfCharge"):
            if not numeric or not 0 <= value <= 100:
                return
            opts["unit_of_measurement"] = "%"
            if path[-1] != "fuelLevel":
                opts["device_class"] = "battery"
        if path == ("charge", "remainTime"):
            if not numeric or not 0 <= value <= 65535:
                return
            opts.update(unit_of_measurement="min", device_class="duration")
        if endpoint == "powertrains" and path[0] == "distanceToEmpties":
            if isinstance(value, bool):
                return
            try:
                value = float(value)
            except (ValueError, TypeError):
                return
            if not math.isfinite(value) or not 1 <= value <= 4095 or unit not in ("feet", "km", "meter", "miles"):
                return
            opts.update(unit_of_measurement=UNITS[unit], device_class="distance", state_class="measurement")
        if endpoint == "driving" and path == ("odometer",):
            if not numeric or not 0 <= value <= 16777214 or unit not in ("km", "mile", "meter", "feet"):
                return
            opts.update(device_class="distance", state_class="total_increasing")
        if endpoint == "status" and path in (("climateControl", "temperature"), ("outsideTemperature",)):
            if not numeric or not -100 <= value <= 100 or unit not in ("C", "F"):
                return
        if endpoint == "status" and path == ("climateControl", "speed"):
            if not numeric or not isinstance(value, int) or not -1 <= value <= 8:
                return
        if endpoint == "freezer" and path == ("freezer", "temperature"):
            if not numeric or not -40 <= value <= 62.3:
                return
            opts.update(unit_of_measurement="°C", device_class="temperature")
        if endpoint == "locations":
            limits = {"latitude": (-90, 90), "longitude": (-180, 180), "altitude": (-100, 10000),
                      "heading": (0, 359), "speed": (0, 1000), "type": (0, 2)}
            field = path[-1]
            if field in limits:
                if not numeric or not limits[field][0] <= value <= limits[field][1]:
                    return
                if field == "type":
                    if not isinstance(value, int):
                        return
                    systems = ["WGS84", "Bessel", "CoordShift"]
                    value = systems[value]
                    opts = {"device_class": "enum", "options": systems}
                elif field in ("latitude", "longitude", "heading"):
                    opts["unit_of_measurement"] = "°"
                elif field == "altitude":
                    opts.update(unit_of_measurement="m", device_class="distance")
                elif field == "speed":
                    if unit not in ("kph", "mph", "mps"):
                        return
                    opts["device_class"] = "speed"
        if path == ("charge", "plugin"):
            if value not in ("connected", "disconnected"):
                return
            value = value == "connected"
            opts["device_class"] = "plug"
        if isinstance(value, bool):
            domain, value = "binary_sensor", "ON" if value else "OFF"
            if path == ("charge", "charging"):
                opts["device_class"] = "battery_charging"
            opts.pop("state_class", None)
        key = identifier(endpoint + "_" + "_".join(map(str, path)))
        result[key] = {"value": value, "name": NAMES.get(key, label(path)), "domain": domain, **opts}

    walk(data)
    return result


def vehicle_id(brand, vin):
    return brand + "_" + hashlib.sha256(vin.encode()).hexdigest()[:16]


def location(data):
    if not isinstance(data, dict) or reported_age(data.get("timestamp")) is None:
        return None
    point = data.get("location")
    if not isinstance(point, dict) or type(point.get("type")) is not int or point.get("type") != 0:
        return None
    lat, lon = point.get("latitude"), point.get("longitude")
    if not all(finite_number(v) for v in (lat, lon)):
        return None
    return point if -90 <= lat <= 90 and -180 <= lon <= 180 else None


# Paths, ranges and units from the four Pleos trip-data response schemas.
TRIP_FIELDS = {
    "powertrains/data": {
        "batteries.hv.voltage": (0, 6553, "V", "voltage"),
        "engine.oilTemperature": (0, 150.5, "°C", "temperature"),
        "engine.rpm": (0, 16383.5, "rpm", None),
    },
    "speed": {
        "location.speed": (0, 254, None, "speed"),
        "location.speedUnit": None,
        **{f"wheel.speed{side}": (0, 511.9375, "km/h", "speed")
           for side in ("FrontLeft", "FrontRight", "RearLeft", "RearRight")},
    },
    "driving/data": {
        "ignition.status": None,
        "odometer.value": (0, 1677721.4, "km", "distance"),
        "acceleration.longitudinal": (-4.177, 4.177, "g", None),
        "angularVelocity.yaw": (-40.95, 40.95, "°/s", None),
        "isla.optionUsm": None,
        "isla.optionUsm2": None,
        "seatbelt.assistance": None,
        "seatbelt.driver": None,
        "steeringWheel.angle": (-3276.8, 3276.7, "°", None),
        "steeringWheel.rotationSpeed": (0, 1016, "°/s", None),
        "transmission.gear": None,
    },
    "status/data": {
        **{f"doors.open{side}": None for side in ("Assistance", "Driver", "RearLeft", "RearRight")},
        "lamp.setting": None,
        **{f"tire.pressure{side}": (0, 254, None, "pressure")
           for side in ("FrontLeft", "FrontRight", "RearLeft", "RearRight")},
        "tire.pressureUnit": None,
        "warnings.lowFuelLevel": None,
        "outsideTemperature.value": (-40, 60, "°C", "temperature"),
    },
}


def trip_readings(endpoint, data):
    """Expose the latest trip's last samples; the API does not supply sample times."""
    trips = data.get("trips") if isinstance(data, dict) else None
    if not isinstance(trips, list):
        return {}, None
    valid = [trip for trip in trips if isinstance(trip, dict) and reported_age(trip.get("triggerStartTime")) is not None]
    if not valid:
        return {}, None
    trip = max(valid, key=lambda t: datetime.fromisoformat(t["triggerStartTime"].replace("Z", "+00:00")))
    start = trip["triggerStartTime"]
    prefix = identifier(endpoint)
    result = {
        prefix + "_trip_start": {"name": label((ENDPOINT_NAMES[endpoint], "start")), "value": start,
                                "device_class": "timestamp", "domain": "sensor", "historical": True},
    }
    length = trip.get("tripLength")
    if finite_number(length) and length >= 0:
        result[prefix + "_trip_duration"] = {
            "name": label((ENDPOINT_NAMES[endpoint], "duration")), "value": length / 1000,
            "unit_of_measurement": "s", "device_class": "duration", "domain": "sensor", "historical": True,
        }

    def samples(path):
        value = trip
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        return value if isinstance(value, list) else []

    for field, spec in TRIP_FIELDS[endpoint].items():
        values = samples(field)
        if not values or values[-1] is None or values[-1] == "invalid":
            continue
        value, index = values[-1], len(values) - 1
        reading = {"name": TRIP_NAMES[field] + " (last trip)", "value": value,
                   "domain": "sensor", "historical": True,
                   "attributes": {"trip_start": start, "trip_length_ms": length, "sample_index": index}}
        if spec is None:
            if not isinstance(value, str) or len(value) > 255:
                continue
        else:
            low, high, unit, device_class = spec
            if not finite_number(value) or not low <= value <= high:
                continue
            if field == "location.speed":
                units = samples("location.speedUnit")
                unit = UNITS.get(units[index]) if len(units) > index and units[index] in ("kph", "mph") else None
                if unit is None:
                    continue
            elif field.startswith("tire.pressure"):
                units = samples("tire.pressureUnit")
                raw_unit = units[index] if len(units) > index else None
                if raw_unit not in ("psi", "kpa", "bar"):
                    continue
                unit = UNITS[raw_unit]
                reading["value"] = value * 5 if raw_unit == "kpa" else value / 10 if raw_unit == "bar" else value
            reading["state_class"] = "measurement"
            if unit:
                reading["unit_of_measurement"] = unit
            if device_class:
                reading["device_class"] = device_class
        result[prefix + "_" + identifier(field)] = reading
    return result, start
