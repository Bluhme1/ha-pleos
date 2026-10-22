# Compared with kia_uvo

[Back to setup guide](../README.md)

[kia_uvo](https://github.com/Hyundai-Kia-Connect/kia_uvo) (Kia Uvo / Hyundai Bluelink) uses [hyundai_kia_connect_api](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api) to talk to the manufacturers' phone-app backends. This integration uses the official Pleos Vehicle Data API. Both can run side by side, with separate devices and credentials.

The Pleos column describes ha-pleos 0.9.0. The kia_uvo comparison was checked against kia_uvo 3.17.1 (library 4.35.2) on 14 October 2026, using its [documented entities](https://github.com/Hyundai-Kia-Connect/kia_uvo#supported-entities) and [trip sensors](https://github.com/Hyundai-Kia-Connect/kia_uvo/blob/master/custom_components/kia_uvo/sensor.py).

## How they connect

| | Pleos Vehicle Data (this integration) | kia_uvo |
| --- | --- | --- |
| API | Official, documented personal API | Unofficial; uses the phone app's backend |
| Login | Personal Client ID and Secret from Pleos Playground, renewed manually | App username and password, sometimes a one-time code |
| Regions | Europe | EU, US, CA, AU, NZ, IN, CN, BR |
| Brands | Hyundai, Kia, Genesis | Kia, Hyundai; Genesis in Canada only (untested) |
| Data freshness | Whatever the car last uploaded; trip data arrives with a delay | Cached data every 30 minutes, plus optional force refresh |
| Wakes the car | Never | On force refresh (every 4 hours by default) |
| Request limits | Not documented; the integration backs off on HTTP 429 | Shares the app backend's limits; force refresh should be used sparingly |
| Remote commands | None (read-only) | Lock, climate, charging, charge limits, windows, horn and lights, schedules, navigation |
| Backend changes | Depends on the official Pleos API | May need library updates when the app backend changes |

## Data

✅ available · 🟡 partial · ❌ not available

| Data | Pleos | kia_uvo |
| --- | :---: | :---: |
| State of charge, range, odometer, fuel level | ✅ | ✅ |
| Range for each powertrain (ICE, EV, HEV, PHEV, hydrogen) | ✅ | 🟡 EV, fuel and total |
| Charging, plugged in, charge limits, time remaining | ✅ | ✅ |
| Charging status including V2L | ✅ | 🟡 V2L and V2X flags |
| Charging power and current | ❌ | ✅ |
| 12 V battery level and warning | ❌ | ✅ |
| Battery state of health, remaining energy | ❌ | ✅ |
| Battery temperatures, chiller, preconditioning, winter mode (newer cars) | ❌ | ✅ |
| Charge port door, charging and departure schedules | ❌ | ✅ |
| Energy consumed and regenerated, 30-day and daily statistics | ❌ | ✅ |
| Location (latitude, longitude) | ✅ | ✅ |
| Altitude, heading, speed | ✅ | 🟡 heading and speed in trip details |
| Doors and locks, bonnet, boot, sunroof | ✅ | ✅ |
| Windows | ❌ | ✅ |
| Tyre pressures | ✅ | ✅ |
| Tyre pressure warnings | ✅ | ✅ |
| Climate state and target temperature | ✅ | ✅ |
| Climate mode and cabin fan speed | ✅ | ❌ |
| Seat heating, steering wheel heating, defrost | ✅ | ✅ |
| Seat ventilation | ✅ | 🟡 in seat status |
| Mirror and rear window heating | ❌ | ✅ |
| Ignition, accessory and high-voltage power states, sleep mode | ✅ | 🟡 no ign1 |
| Warnings | ✅ individual warnings and full list | ✅ individual warnings |
| Lights (turn signals, brake lights, headlights) | 🟡 light switch setting during trips | ✅ |
| Service intervals, fault code count | ❌ | ✅ |
| Reporting time and data age for each data group | ✅ | 🟡 last updated, location updated |
| Trip summaries (distance, duration) | ✅ | 🟡 trip details and daily statistics |
| Trip sample series (wheel speeds, RPM, HV voltage, acceleration, yaw, steering, gear, seat belts) | ✅ | ❌ |
| Trip events with every sample, per-trip min, max and mean | ✅ | ❌ |
| Freezer (Kia PV5) | ✅ | ❌ |
| 360° camera images | ❌ | ✅ Hyundai |

Availability depends on the vehicle, model year and region in both integrations. Marks describe the documented entities and trip attributes; either API may return additional fields.

ha-pleos also provides [Estimated EV consumption](entities.md#estimated-ev-consumption) from battery percentage, capacity and odometer changes. This is a calculated estimate; Pleos does not report the consumed or regenerated energy totals listed above.
