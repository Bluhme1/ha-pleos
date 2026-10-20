# Pleos Vehicle Data

[![Validate](https://github.com/jouwdan/ha-pleos/actions/workflows/validate.yml/badge.svg)](https://github.com/jouwdan/ha-pleos/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/jouwdan/ha-pleos)](https://github.com/jouwdan/ha-pleos/releases/latest)
[![HACS custom integration](https://img.shields.io/badge/HACS-Custom_Integration-41BDF5)](https://www.hacs.xyz/docs/faq/custom_repositories/)

A Home Assistant integration for the official Pleos **personal Vehicle Data API**. Supports Hyundai, Kia and Genesis accounts, with one entry per account and a device for each vehicle. Requires Home Assistant **2026.10 or later**.

API communication is provided by the independent [`pleos-client`](https://github.com/jouwdan/pleos-client) Python library. Home Assistant installs the pinned dependency automatically. Entities, polling schedules, retained readings, trip history and diagnostics remain in this integration.

## Contents

- [Supported vehicles](#supported-vehicles)
- [Install with HACS](#install-with-hacs)
- [Install without HACS](#install-without-hacs)
- [Set up your account](#set-up-your-account)
- [Options](#options) — all settings at a glance
- [Data available in Home Assistant](#data-available-in-home-assistant)
- [Example dashboard](#example-dashboard)
- [No vehicles](#no-vehicles)
- [Expired or replaced API keys](#expired-or-replaced-api-keys)
- [Compared with kia_uvo](#compared-with-kia_uvo)
- [Limitations and privacy](#limitations-and-privacy)

## Supported vehicles

**Tested and working with a Kia PV5 Passenger.** Available fields depend on the data returned by the vehicle's API.

Pleos documents access to European vehicles using **Hyundai Bluelink, Kia Connect or Genesis Connected services**. See the [official supported-country list](https://document.pleos.ai/en/api-reference/vehicle-data-api/faq).

The following models and variant labels appear in the [Vehicle Data API compatibility matrix](https://document.pleos.ai/en/api-reference/vehicle-data-api/api-compatibility), checked **12 October 2026**:

| Manufacturer | Documented models and variants |
| --- | --- |
| Hyundai | ELANTRA (NORMAL); INSTER (EV); IONIQ 5 (EV); IONIQ 6 (EV); IONIQ (EV, HEV, PHEV); KONA Electric (HEV); KONA N (NORMAL); KONA (EV, HEV, NORMAL); NEXO (FCEV); SANTA FE (HEV, NORMAL, PHEV); STARIA (HEV, NORMAL); TUCSON (HEV, NORMAL, PHEV); i10 (NORMAL); i20 / BAYON (NORMAL); i20 N (NORMAL); i30 N (NORMAL); i30 (NORMAL) |
| Kia | CEED (NORMAL, PHEV); EV3 (EV); EV6 (EV); EV9 (EV); NIRO (EV, HEV, PHEV); Picanto (NORMAL); SORENTO (HEV, NORMAL, PHEV); SOUL EV (EV); SPORTAGE (HEV, NORMAL, PHEV); STINGER (NORMAL); STONIC (NORMAL) |
| Genesis | G70 (NORMAL); G80 (EV, NORMAL); G90 (NORMAL); GV60 (EV); GV70 (EV, NORMAL); GV80 (NORMAL) |

These are Pleos's labels, including “KONA Electric (HEV)”; the matrix does not specify model years. The integration discovers cars through [Get Vehicles](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/for-private-users/get-vehicles), so other models may work too. Available fields vary by vehicle.

## Install with HACS

The [default-list submission](https://github.com/hacs/default/pull/11971) is awaiting review. Until it is included, install this as a custom integration:

1. [Install and configure HACS](https://www.hacs.dev/docs/use/download/download/) if required.
2. Open **HACS → ⋮ → Custom repositories**. Add `https://github.com/jouwdan/ha-pleos` with type **Integration**.
3. Find **Pleos Vehicle Data**, download it, then restart Home Assistant.
4. Complete the setup below. HACS manages later integration downloads and updates.

## Install without HACS

1. Download the source ZIP from the [latest release](https://github.com/jouwdan/ha-pleos/releases/latest).
2. Extract it and copy `custom_components/pleos_vehicle_data` into your Home Assistant configuration directory's `custom_components` folder. The result must be `<config>/custom_components/pleos_vehicle_data/manifest.json`.
3. Restart Home Assistant and complete the setup below. For updates, replace that integration directory with the new release and restart.

## Set up your account

The private API only allows the vehicle's **primary user** to authorise access. Shared or secondary app users cannot authorise a vehicle, even if they can see it in the manufacturer's app. Generate the key using the primary user's manufacturer account.

1. Sign into [Pleos Playground](https://pleos.ai/). Open the account menu → **My Vehicle Data API**. This menu is available to users in Europe.
2. Select the manufacturer, accept the required terms, choose **Get API Key**, and sign into the manufacturer's account. Copy **Client ID** and **Client Secret**. Private users do not need a business project or API-access approval. [Official key-generation guide](https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/request-my-vehicle-api-key).
3. In Home Assistant, open **Settings → Devices & services → Add integration → Pleos Vehicle Data**. Select that manufacturer and enter both credentials. Setup validates them before saving.
4. Add the car's entities to dashboards or automations. Repeat setup for another account, including another account from the same manufacturer.

Each account has separate devices, readings, options, trip history and archive storage. Additional entries are named **Kia 2**, **Kia 3**, and so on; you can rename them in Home Assistant. Adding the same API key twice is rejected. To replace an existing account's credentials, use **⋮ → Reconfigure** on that entry instead of adding it again. Different keys are treated as separate accounts, even if they grant access to the same car.

Existing installations keep their entity and device IDs, statistics and archive paths. Replacing credentials keeps those identities for both existing and newly added accounts.

## Options

All settings are in one place: **Settings → Devices & services → Pleos Vehicle Data → Configure** on an account entry. The dialog has three sections, **Vehicle status**, **Trips** and **Storage**. Changes reload the integration. Everything not listed here works without configuration, including the **Trip** event entity and the trip statistics.

| Section | Option | Default | Range | Effect |
| --- | --- | --- | --- | --- |
| Vehicle status | **Polling interval** | 15 min | 5–1440 min | How often status data is requested. The car uploads on its own schedule, so polling more often does not make data newer. |
| Vehicle status | **Stale-data threshold** | 60 min | 5–10080 min | Readings older than this get `data_stale: true`. They stay available. |
| Vehicle status | **Enable location data and GPS tracking** | On | | Requests the location endpoint and creates the GPS tracker. Off: neither. |
| Vehicle status | **Correct odometer kilometres labelled as miles** | No cars selected | Per car | Treats a selected car's snapshot odometer value as kilometres when the API labels it miles. Use only for a confirmed unit-label error; see [Units](#units). |
| Trips | **Trip data interval** | 60 min | 5–1440 min | How often the four trip endpoints are requested. Failed trip requests retry at the next status poll. |
| Trips | **Fire an event for each new trip** | Off | | Fires `pleos_vehicle_data_trip` with every sample; see [Trip events](#trip-events). The **Trip** event entity works regardless of this option. |
| Storage | **Archive raw vehicle data** | Off | | Keeps raw responses in compressed files; see [Response archive](#response-archive). |

Credentials are not options: replace them with **⋮ → Reconfigure**; see [Expired or replaced API keys](#expired-or-replaced-api-keys).

## Refresh on demand

Use the **Pleos Vehicle Data: Refresh** action (`pleos_vehicle_data.refresh`) in Home Assistant's action editor or an automation, and select the **Account** to refresh. It requests another poll of that account without waiting for its normal polling interval. Repeated requests are batched, and trip polling intervals and API rate-limit backoff still apply.

This fetches data already available in Pleos. It cannot wake the car or make it upload new readings, so the returned values may be unchanged.

## Data available in Home Assistant

All ten common Vehicle Data API endpoints are queried. Fields appear when the API supplies valid values for the vehicle.

| API | Endpoint suffix | Exposed data |
| --- | --- | --- |
| [Battery charging](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-battery-charging-status) | `batteries` | Plug connection, charging state, charge percentage, capacity, charge targets and remaining charge time |
| [Powertrain status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-powertrain-status) | `powertrains` | Fuel level, battery percentage and remaining range |
| [Location](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-location-info) | `locations` | Coordinates, coordinate system, altitude, heading and speed; GPS tracker for valid WGS84 coordinates |
| [Driving status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-operation-status) | `driving` | Ignition, power states, sleep mode, odometer and parking position |
| [Vehicle status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-status) | `status` | Doors, bonnet, boot, sunroof, tyres, warnings (full list and count as attributes), climate, defrost, steering-wheel heat, seats and outside temperature |
| [Freezer status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-freezer-status) | `freezer` | Operation state and temperature |
| [Powertrain trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-powertrain-data) | `powertrains/data` | Battery voltage, engine oil temperature and RPM samples |
| [Speed trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-speed-data) | `speed` | Dashboard speed, units and four wheel-speed series |
| [Driving trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-operation-data) | `driving/data` | Ignition, mileage, trip distance, acceleration, yaw, ISLA settings, seat belts, steering and gear samples |
| [Vehicle status trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-data) | `status/data` | Door, lamp, tyre-pressure, low-fuel-warning and outside-temperature samples |

Each endpoint has an **API diagnostic sensor** showing `available`, `no_data`, `error` or `disabled`. Permission and unregistered-vehicle errors show `error`; code `4045` means `no_data`. The `data` attribute holds the complete vehicle payload, including fields without a dedicated sensor, and `api_metadata` holds response metadata.

The `rejected_values` and `rejected_examples` attributes explain discarded readings, such as values outside the documented range or in an unknown unit. Empty fields and the API's `invalid` markers are not counted. Debug logs include the field and reason without the raw value. The **Vehicle information** sensor exposes VIN, nickname, model and powertrain details, plus other fields returned by Get Vehicles.

Trip queries run every **60 minutes** by default, separately from status polling, and normally cover **yesterday and today in UTC**. After a gap, they reach back to the last successful fetch, up to **7 days** including today. First setup also checks this wider window. If Pleos refuses the range, the integration retries with two days. The diagnostic sensor's `query` attribute shows the dates requested.

Trip sensors keep their results between queries. New vehicles are queried immediately; failed requests retry on the next status poll. `no_data` results wait for the normal trip interval. Pleos delivers trips with a delay, so polling more often may return the same data.

Full returned trips remain in the diagnostic sensor's `data` attribute. Individual trip sensors show the latest trip's final sample when valid, with trip start, duration and sample index.

Numeric trip sensors have `trip_min`, `trip_max`, `trip_mean`, `valid_samples` and `total_samples` attributes. Summaries use valid samples in the final sample's unit; the mean is per sample, not time-weighted. Home Assistant can convert the sensor state to your preferred unit without converting these attributes. Each endpoint reports its own latest trip, so its readings may refer to a different drive.

**Trip distance (last trip)** is the difference between the first and last valid odometer samples of the latest driving trip. Its `odometer_start` and `odometer_end` attributes are in kilometres. An invalid final sample does not become a reading. Undocumented fields also get **(last trip)** readings, with numeric summaries where possible. Individual samples have no documented timestamps.

Status endpoints have reporting-time and data-age sensors when the vehicle supplies a valid timestamp. Readings stay visible while the car is parked; check `reported_at`, `data_age_minutes` and `data_stale` for their age. Turning off location in the [options](#options) disables both location requests and GPS tracking.

If the initial account request fails with a connection error, rate limit or server error, existing vehicle readings stay visible until a poll succeeds. This includes location, status and diagnostic readings from the last completed poll. They get `last_known: true` and `data_stale: true`, keeping their original values, units and reporting times. The **Connection** sensor still reports the failure, **Last successful poll** does not advance, and downloaded diagnostics show `last_update_success: false` and `using_last_data: true`. Authentication, permission, invalid-response and unexpected failures still make readings unavailable; a successful poll is required before retention can resume.

During connection failures, rate limits and server errors on an individual endpoint, the last valid battery levels, charge limits, fuel level, odometer, temperatures and tyre pressures remain visible with `last_known: true` and `data_stale: true`. Their age and `reported_at` still refer to the original vehicle reading, and endpoint diagnostics continue to show the error. Successful responses replace these values and clear the retention marker. Permission errors, `no_data`, and missing or invalid fields in successful responses do not retain these measurements. Locks, doors, warnings, charging/ignition status, charge time remaining and location are not retained.

These readings are retained only in memory, until a reload or restart; [driving ranges](#driving-ranges) have separate persistent restoration. Retained values can remain indefinitely during an outage, so automations needing current data must check `data_stale`, including before using a retained location, lock or charging state.

Entities use names such as **AC charge limit** and **Cabin fan speed**; historical readings include **(last trip)**. Name changes preserve existing IDs and customised names. Documented fields support Home Assistant translations, with English included. New IDs use the English name regardless of your display language. Undocumented fields use names derived from their API paths.

### Entities and devices

Each account entry creates an **API device** (for example *Kia API* or *Kia 2 API*) and one device per car.

| Device | Entity | What it shows |
| --- | --- | --- |
| API device | **Connection** | `connected`, `no_vehicles` (the key works but grants no car; see [No vehicles](#no-vehicles)), `key_required` (replace the personal key), `api_unavailable` (Pleos could not be reached) or `rate_limited` (Pleos asked to slow down; requests pause until it allows them again) |
| API device | **Archive** | Only when the archive is enabled: `ok` or `error`, with the folder, last write and last error |
| API device | **Last successful poll** | When Home Assistant last completed this account's poll without request errors. This is the fetch completion time, not when the car uploaded its data. |
| Car | Readings | One sensor or binary sensor per value the API returns, for example **Battery level**, **Odometer**, **Front left door** |
| Car | **(last trip)** sensors | The latest trip's final sample per trip field, with summaries (see above) |
| Car | **Trip** | Event entity firing once per trip; see [Trip event entity](#trip-event-entity) |
| Car | **Location** | GPS tracker, when location is enabled and the car reports valid WGS84 coordinates |
| Car | **Vehicle information** | Diagnostic: powertrain type, with VIN, model and every other Get Vehicles field as attributes |
| Car | ***Endpoint* API** | Diagnostic, one per endpoint: `available`, `no_data`, `error` or `disabled`, with the raw response, query and rejected values (see above) |
| Car | ***Endpoint* last reported**, ***Endpoint* data age** | Diagnostic, per status endpoint: when the car last reported that data and how old it is |

**Last successful poll** advances only when the vehicle list and all endpoints requested in that poll finish without errors. Disabled endpoints, trip data reused between scheduled trip polls, and an API `no_data` result do not count as failures. Authentication, connection, rate-limit and individual endpoint errors leave the timestamp unchanged. It remains visible during failures and starts unknown after setup/reload until a poll succeeds. Check each car's **last reported** and **data age** sensors for the age of the actual vehicle readings; a successful poll can return old data.

### On/off readings and upgrading to 0.7.0

Ignition, ignition power, high-voltage system power, accessory power, sleep mode, climate control, windscreen defrost, steering wheel heating and freezer operation are native binary sensors. They report `on` or `off`, allowing Home Assistant to colour active dashboard icons. Missing, invalid or unexpected values do not become `off`. These readings reflect the latest cloud report; ignition can be on while the vehicle is parked.

**Upgrading from 0.6.0 or earlier:** these nine readings move from `sensor.*` to `binary_sensor.*`. After updating and restarting Home Assistant, find their new entity IDs on the vehicle's device page and update dashboard cards, automations and scripts that use the old IDs. For example, `sensor.ev6_ignition` becomes `binary_sensor.ev6_ignition` with the default names. In a picture-elements `state-icon`, use the new entity and `state_color: true`.

Home Assistant registers these as new entities. Custom entity IDs, names, icons, areas and disabled/hidden settings on the old sensors are not copied; reapply the settings you need. Old sensor entries may remain unavailable and can be removed after you update their references. Existing history is not moved to the new entities. The [example dashboard](examples/dashboard.yaml) uses the new IDs.

The 0.7.0 release left other text readings unchanged; 0.8.0 extends the conversions below.

### Native entities and upgrading to 0.8.0

**Bonnet**, **Boot** and **Sunroof** are now open/closed binary sensors. Bonnet and boot use Home Assistant's `opening` device class; sunroof uses `window`. Update references from `sensor.<car>_bonnet`, `sensor.<car>_boot` and `sensor.<car>_sunroof` to their new `binary_sensor.*` IDs after updating and restarting Home Assistant. As with the 0.7.0 conversions, reapply customisations to the new entities; old entries and history are not automatically deleted or moved. Their raw states are now `on` (open) and `off` (closed).

Doors, seat heating/ventilation levels, climate mode and detailed charging status are **enum sensors** with predefined states and translated display labels. Their entity IDs stay the same. Door states retain `open`, `closed` and `locked`; seat levels retain `off`, `low`, `middle` and `high`; climate mode retains `manual`, `auto`, `off` and `error`. Unknown values become unavailable instead of being interpreted as off or closed.

**Charging status raw states change in 0.8.0.** Update state comparisons in automations, scripts and templates:

| Previous raw state | New raw state |
| --- | --- |
| `notCharging` | `not_charging` |
| `charging` | `charging` |
| `fastCharging` | `fast_charging` |
| `v2lOperating` | `v2l_operating` |
| `v2lStop` | `v2l_stop` |
| `v2xOperating` | `v2x_operating` |
| `reservedCharging` | `reserved_charging` |
| `wirelessCharging` | `wireless_charging` |

The 17 [documented warning indicators](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-status) each get a `problem` binary sensor, including **Low fuel warning**, **Key battery warning**, **Washer fluid warning**, **Brake fluid warning**, **Engine oil warning**, tyre-pressure warnings and lamp warnings. They show `on` when that warning is reported and `off` when absent from a valid warning list. An empty list clears them all. Missing, invalid or malformed warning data, or a failed status-endpoint request, makes them unavailable. A transient failure of the initial account request still retains the previous whole poll with `last_known: true` and `data_stale: true`, as described above. These indicate what the last vehicle report says, not an independent health check.

The existing **Warnings** sensor still keeps the full list and count, including unrecognised codes. Warning sensors appear only once a valid warning list has been received.

**AC charge limit** and **DC charge limit** are ordinary percentage sensors, not battery-level sensors. This prevents Home Assistant's device-page battery indicator from selecting a charge target such as 100%. Actual **Battery level** and **Traction battery level** retain the battery device class. Charge-limit IDs, values, history and retention during transient failures are preserved.

**Cabin fan speed** keeps its entity ID but becomes an enum: numeric `-1` becomes `auto`, `0` becomes `off`, and `1`–`8` become `level_1`–`level_8`. Update numeric state comparisons. Display labels are Auto, Off and Level 1–8.

Six **(last trip)** readings also move from `sensor.*` to `binary_sensor.*`: **Ignition**, **Driver door**, **Front passenger door**, **Rear left door**, **Rear right door** and **Low fuel warning**. Their suffix remains `_last_trip`; for example, `sensor.<car>_driver_door_last_trip` becomes `binary_sensor.<car>_driver_door_last_trip`. Doors use `on` for open and `off` for closed; ignition and the warning use `on` for active. Reapply customisations and update references as for bonnet/boot/sunroof. These are historical samples, not current vehicle status.

Last-trip **Gear**, **Seat belts**, **Speed limit assist settings**, **Exterior light setting**, **Speed unit** and **Tyre pressure unit** become enums while keeping their IDs. Gear raw states remain `p`, `r`, `n`, `d`, displayed as Park, Reverse, Neutral, Drive. Seat belts retain `belted`/`unbelted`; an unfastened belt does not establish occupancy or danger. Light-setting raw states change: `lightSwOff` → `off`, `tailSwOn` → `tail_lights`, `headLampLowSwOn` → `headlamps`, `autoLightSwOn` → `auto`. The **Trip** event's text attributes and raw trip events retain their original API values.

The full entity mapping is:

| Readings | Home Assistant representation |
| --- | --- |
| Actual charge percentages | `battery` measurement sensors, % |
| AC/DC charge limits; fuel level | Percentage sensors; target icons for charge limits and fuel-pump icon for fuel |
| Plug connection; charging | `plug` and `battery_charging` binary sensors |
| Bonnet, boot; sunroof | `opening` and `window` binary sensors |
| Ignition and ignition/accessory power | `power` binary sensors |
| Climate/freezer operation | `running` binary sensors |
| Sleep mode, in park, defrost, steering-wheel heating | On/off binary sensors with matching icons |
| Doors, seat levels, climate mode, fan level, charging status | Enum sensors preserving the documented states |
| Individual warnings | `problem` binary sensors; full warning list retained separately |
| Ambient, freezer and oil temperatures; cabin target temperature | `temperature` sensors; the cabin target is a setting, not a measurement |
| Tyre pressures; battery voltage | `pressure` and `voltage` sensors with validated units |
| Odometer | `distance` sensor with `total` state class for lifetime mileage |
| Remaining ranges; altitude | `distance` sensors; ranges are estimates |
| Speed and wheel speeds | `speed` sensors |
| Charge time remaining; trip duration | `duration` sensors |
| GPS location; latitude/longitude; heading | GPS tracker; degree-valued coordinates; angle measurement for heading |
| Coordinate system; trip speed/pressure unit | Diagnostic enums |
| Trip ignition, doors and low-fuel warning | Historical `power`, `door` and `problem` binary sensors |
| Trip gear, belts, ISLA and light settings | Historical enums |
| RPM, acceleration, steering angle and angular rates | Numeric sensors with their documented units; HA has no matching device class for these units |
| Battery capacity | Plain numeric sensor: Pleos does not document its energy unit, so none is guessed |
| API connection/endpoint/archive status; reporting times | Diagnostic enums and timestamp sensors |
| Vehicle information; data age | Diagnostic text/attributes and minutes |
| Undocumented fields | Plain readings until their meaning and units are documented |

Only current measurements generate measurement statistics. Charge targets, cabin temperature targets, range/time estimates, capacity, coordinates, data age and delayed **(last trip)** readings no longer generate new measurement statistics. Their ordinary state history remains; existing statistics are not deleted or rewritten. Heading uses angular statistics so 359° and 1° average around north. Odometer uses `total` because lifetime mileage does not periodically reset. The separate [trip statistics](#trip-statistics) continue to record distance, driving time and speed against the hour driven.

These remain read-only entities. The API does not support operating locks, windows, heating or fans, so they are not exposed as controllable switches, covers, locks, fans or climate entities.

### Units

Status readings use the unit returned by the API. For example, the [odometer response](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-operation-status) can report `km`, `mile`, `meter` or `feet`; these become Home Assistant's `km`, `mi`, `m` or `ft`. Trip odometer samples are documented in kilometres.

Some vehicles return a kilometre odometer value labelled `mile` ([#6](https://github.com/jouwdan/ha-pleos/issues/6)). If **Driving status API → data.odometer** contains `5177.5` with unit `mile`, but the car shows about `3217` miles, select that car under **Configure → Vehicle status → Correct odometer kilometres labelled as miles**. Home Assistant will interpret the value as `5177.5 km` and display about `3217.15 mi` when miles are selected. Raw API diagnostics and archives stay unchanged; the corrected Odometer entity includes `api_unit_of_measurement: mi`.

Leave this option empty for correctly reported odometers. It applies only to the selected cars' snapshot odometers labelled miles; trip data and other units are unaffected. Clear the selection if Pleos fixes the underlying data. Existing history and statistics are not rewritten. A correction changes the recorded total, so check **Developer tools → Statistics** for affected odometer totals after enabling it.

Home Assistant converts readings for your unit preferences. To display miles, open the odometer entity's settings and set **Unit of measurement** to **mi**. This converts both the number and label: **1,609.344 km = 1,000 mi**. If a reading differs from the car or app, compare its value and unit with `data.odometer` on the **Driving status API** sensor and include both in an issue report.

### Driving ranges

Range readings accept both `mile` and `miles`, alongside `km`, `meter` and `feet`. Home Assistant converts their values for your selected display unit.

When the API returns several ranges with the same type, each has its own sensor. The existing unnumbered sensor shows the first entry of that type; subsequent entries are named **Plug-in hybrid range 2**, **Plug-in hybrid range 3**, and so on. Previously, the last entry overwrote the earlier ones. Numbering follows the API's order, including entries whose values are missing or invalid; it does not identify petrol versus electric range. If the API changes the order, the numbered readings follow that change.

The last valid range and its native unit are saved per vehicle and sensor, including across restarts. If a later response omits it, contains a dash or an invalid value, lacks a valid timestamp, or the powertrain request fails, the saved range stays visible with `last_known: true` and `data_stale: true`. Its `reported_at` and `data_age_minutes` refer to the original reading, not the latest poll. A new valid reading clears `last_known`; the usual stale-data threshold still applies. Raw API diagnostics and archives remain unchanged, and the **Powertrain status API** sensor still reports request errors.

Saved ranges can remain visible indefinitely while the vehicle is still on the account. Automations needing current data should check `data_stale`. Transient account failures retain ranges already loaded in memory; after a reload, the initial account request must succeed before saved ranges can be restored. Authentication and permission failures still make vehicle readings unavailable. Removing a vehicle from the API's vehicle list clears its saved ranges; removing the integration clears this saved data too.

### Trip events

Enable **Trip events** in the [options](#options) to fire a `pleos_vehicle_data_trip` event for each new trip. It is off by default. Events contain every returned sample for use in automations or exports, for example through Node-RED or AppDaemon:

| Key | Content |
| --- | --- |
| `vehicle_id` | Stable vehicle ID used by this integration (not the VIN) |
| `device_id` | Home Assistant device, once the vehicle's device exists |
| `brand` | `hyundai`, `kia` or `genesis` |
| `endpoint` | `powertrains/data`, `speed`, `driving/data` or `status/data` |
| `trip_start`, `trip_length_ms` | Trip start time and duration as returned |
| `trip` | The complete trip object, including all sample arrays |

Trips are identified by start time, vehicle and endpoint. Each endpoint sends its own event, including for late arrivals within the query window. Sent trips are remembered across restarts for nine days. Events fire after a complete poll; first setup sends events for trips already in the window.

The recorder stores events, including their sample arrays. To keep them out of the database, add this to `configuration.yaml`:

```yaml
recorder:
  exclude:
    event_types:
      - pleos_vehicle_data_trip
```

Sensor history contains the latest trip at each poll, so several trips arriving together produce one latest-trip state. To record every trip, use the **Trip** event entity below; for every sample, use trip events or the archive.

### Trip event entity

Each car has a **Trip** event entity (`event.<car>_trip`). It fires once for every trip the API returns, oldest first, also when several trips arrive in one query and for trips found at setup or by the catch-up after downtime. Each firing is an ordinary recorded state change, so Home Assistant's history and its InfluxDB integration keep every trip, and automations can trigger on it.

- `event_type`: `powertrains_data`, `speed`, `driving_data` or `status_data`, the trip endpoint the trip came from. A drive usually appears once per endpoint.
- Attributes: `trip_start` (the drive's start), `duration_s`, `distance_km` (driving trips), and each trip field named like its **(last trip)** sensor without the endpoint prefix, for example `location_speed`, with `_min`, `_max` and `_mean` for numbers. Units are those of the matching sensor. Sample arrays are not included.
- The event's own time is when Home Assistant received the trip, not when it was driven; use `trip_start` for the drive time.
- Fired trips are remembered across restarts for nine days. After a restart, Home Assistant restores the last event with its original time; that is not a new trip.

### Trip statistics

Trips reach Home Assistant up to a day after the drive, so sensor states and Trip events carry the time they arrived. For correct daily and hourly figures, the integration also imports **long-term statistics at the hour each trip started**:

| Statistic ID | Content | Type |
| --- | --- | --- |
| `pleos_vehicle_data:<vehicle>_distance` | Distance driven, from driving trips' odometer samples | Sum, km |
| `pleos_vehicle_data:<vehicle>_driving_time` | Driving time, from driving trips' duration | Sum, min |
| `pleos_vehicle_data:<vehicle>_speed` | Speed while driving, from speed trips' samples | Hourly mean, minimum and maximum, km/h |

`<vehicle>` is this integration's vehicle ID (not the VIN). Show them with a **Statistics graph** card, for example kilometres per day:

```yaml
type: statistics-graph
title: Distance per day
entities:
  - pleos_vehicle_data:kia_0123456789abcdef_distance
stat_types:
  - change
period: day
chart_type: bar
```

- Pleos gives no time per sample, so a whole trip counts in the hour it started.
- A trip that arrives late, or again with more samples, corrects its hour; all later sums are imported again, so totals stay right.
- Every returned trip counts, including trips found at setup or by the catch-up after downtime. Earlier drives are not imported.
- Statistics are kept in Home Assistant's database and shown in its statistics graphs and **Developer tools → Statistics**. The InfluxDB integration does not export them.
- Removing the integration also removes these statistics.

### Response archive

The optional archive keeps raw snapshot payloads and trip objects, including fields this integration does not understand yet. The archive is off by default and can be enabled under **Storage** in the [options](#options).

- Files: `<config>/pleos_vehicle_data/archive/<account>/<YYYY-MM>/<YYYY-MM-DD>.jsonl.gz`, one gzip-compressed JSON object per line, by UTC day of the request. Existing entries keep their manufacturer folder; new entries get a separate account folder. The **Archive** sensor shows the exact path.
- A snapshot or the vehicle list is written when its content changes; an unchanged response is not written again. Each trip is written once, and again only if Pleos later returns different content for it. Restarts do not cause duplicates.
- Each record has `schema`, `kind` (`vehicles`, `snapshot`, `trip` or `trip_response`), `fetched_at`, `endpoint`, `vehicle_id`, the trip `query` and the API's `api_metadata`, plus the response in `data` or the trip in `trip`.
- Files remain until you delete them, including after removing the integration. Read them with `zcat`, `zgrep` or Python's `gzip.open`.
- The **Archive** diagnostic sensor on the account's API device shows `ok` or `error`, the folder, the last write and the last error.

The archive contains the VIN in the vehicle list and the car's locations. Treat the folder like the rest of your Home Assistant configuration.

### Diagnostics

Use **Settings → Devices & services → Pleos Vehicle Data → ⋮ → Download diagnostics** for troubleshooting. It includes options, polling and rate-limit status, trip windows, archive status, readings and raw responses. A download from a car's device page contains only that car. Credentials, VINs, nicknames and coordinates are removed. Review the file before attaching it to an issue, especially if the API adds new fields.

## Example dashboard

[`examples/dashboard.yaml`](examples/dashboard.yaml) uses built-in cards for charge, range, doors, climate, a 48-hour map, trip summaries, 7-day graphs and data age.

1. Replace `my_car_` with your car's entity-ID prefix and `hyundai_api_` with `kia_api_` or `genesis_api_` if needed. Check the full IDs against your entity list: older installations and customised IDs may also have different suffixes. Update these in both cards and markdown templates; some templates assemble IDs from a prefix and suffix.
2. In Home Assistant, add a dashboard, open it, then choose **⋮ → Edit → ⋮ → Raw configuration editor** and paste the file.

Missing tiles, gauges, map and badges are hidden outside edit mode. Trip cards fill in as valid samples arrive; graphs need recorded history. Missing trip distance is shown as unavailable. Summary tables label API units separately from converted sensor states. The VIN is masked to its last six characters.

## No vehicles

If the **Connection** sensor shows `no_vehicles`, Pleos accepted the key but returned no car for it. The integration cannot change this; the cause is on the account or vehicle side. Known causes:

- **Not the primary user.** Only the vehicle's primary user can authorise API access. A key created with a shared or secondary app account grants no car, even if that account sees the car in the app.
- **Key created before the car was added or activated.** Vehicle access is fixed when the key is issued. Generate a new key after the car appears in the manufacturer's app, then replace both credentials with **⋮ → Reconfigure**.
- **Vehicle locked by the manufacturer.** Former company, fleet or demonstration cars can remain restricted in the manufacturer's systems, so the API returns no vehicle even for the primary user. Other Pleos-based integrations show the same. Only the manufacturer's customer support or Pleos can lift this.
- **Region or connected services.** The personal API is only available in Europe, and the car's connected services and data-sharing consent must be active.

The diagnostics download then shows `"status": "no_vehicles"` and no cars. When asking for help, attach it; it removes credentials and VINs.

## Expired or replaced API keys

Personal keys expire and require **manual renewal**. Check the expiry shown in Pleos. The integration renews access tokens automatically, not the personal key. [Official key-management guide](https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/manage-my-vehicle-api-key).

Expired access tokens are replaced automatically and the failed request is retried once. A 403 that persists with a fresh token remains an API permission error; it does not ask you to replace a valid personal key.

When credentials are rejected, polling stops and Home Assistant requests reauthentication. Generate a new personal key and replace **both Client ID and Client Secret** in that request. To replace credentials before expiry, use the account entry's **⋮ → Reconfigure** menu. The existing entry reloads and retains entity IDs for the same vehicles.

Pleos invalidates old access tokens when a key expires, is revoked or is reissued. A newly registered or activated vehicle also needs a new key: vehicle access is fixed at issuance. [Get Vehicles rules](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/for-private-users/get-vehicles).

## Compared with kia_uvo

[kia_uvo](https://github.com/Hyundai-Kia-Connect/kia_uvo) (Kia Uvo / Hyundai Bluelink) uses [hyundai_kia_connect_api](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api) to talk to the manufacturers' phone-app backends. This integration uses the official Pleos Vehicle Data API. Both can run side by side, with separate devices and credentials.

Compared with kia_uvo 3.17.1 (library 4.35.2) on 14 October 2026, using its [documented entities](https://github.com/Hyundai-Kia-Connect/kia_uvo#supported-entities) and [trip sensors](https://github.com/Hyundai-Kia-Connect/kia_uvo/blob/master/custom_components/kia_uvo/sensor.py).

### How they connect

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

### Data

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
| Tyre pressure warnings | ❌ | ✅ |
| Climate state and target temperature | ✅ | ✅ |
| Climate mode and cabin fan speed | ✅ | ❌ |
| Seat heating, steering wheel heating, defrost | ✅ | ✅ |
| Seat ventilation | ✅ | 🟡 in seat status |
| Mirror and rear window heating | ❌ | ✅ |
| Ignition, accessory and high-voltage power states, sleep mode | ✅ | 🟡 no ign1 |
| Warnings | 🟡 list (such as washer fluid, low fuel) | ✅ individual warnings |
| Lights (turn signals, brake lights, headlights) | 🟡 light switch setting during trips | ✅ |
| Service intervals, fault code count | ❌ | ✅ |
| Reporting time and data age for each data group | ✅ | 🟡 last updated, location updated |
| Trip summaries (distance, duration) | ✅ | 🟡 trip details and daily statistics |
| Trip sample series (wheel speeds, RPM, HV voltage, acceleration, yaw, steering, gear, seat belts) | ✅ | ❌ |
| Trip events with every sample, per-trip min, max and mean | ✅ | ❌ |
| Freezer (Kia PV5) | ✅ | ❌ |
| 360° camera images | ❌ | ✅ Hyundai |

Availability depends on the vehicle, model year and region in both integrations. Marks describe the documented entities and trip attributes; either API may return additional fields.

## Limitations and privacy

- Default polling is **15 minutes**. After **60 minutes**, snapshot readings are marked `data_stale: true` but remain available. Both are configurable; see [Options](#options). Age is updated at each poll. Transient account failures keep existing readings marked stale; missing or invalid readings, authentication failures and permission errors can still make entities unavailable. Automations that require recent information should check `data_stale`.
- Availability varies with vehicle, powertrain, model year, region and connected-service settings. Null or documented invalid values do not become vehicle readings. `no_data` is an API result, not a guarantee of future availability. [Pleos FAQ](https://document.pleos.ai/en/api-reference/vehicle-data-api/faq).
- Pleos says trip data is available only **24 hours after consent**, and also depends on connected services, data-collection consent and ePrivacy settings. A `4045` response means no data was returned. [Pleos FAQ](https://document.pleos.ai/en/api-reference/vehicle-data-api/faq).
- This is a read-only cloud integration. It does not implement remote vehicle commands, camera access, the in-car SDK, Fleet API or business-user authentication/consent flows. Status snapshots and returned trip samples are not live telemetry.
- A failing optional endpoint, including a timeout, does not hide other endpoint data. Rate limits stop remaining requests and keep readings already fetched in that poll; affected readings may be unavailable until recovery. Account-level failures are reported by the Connection sensor. Requests retry on later polls and respect `Retry-After`. Responses above **16 MiB** are rejected.
- Keys live in Home Assistant's private configuration; access tokens stay in memory. Credentials and VINs are not logged. Raw payloads and VIN attributes are excluded from recorder history, but remain accessible in current entity attributes. Protect configuration files and backups.

Trip features, translations, diagnostics and the example dashboard contributed by [Alex (@isarrider)](https://github.com/isarrider) in [PR #5](https://github.com/jouwdan/ha-pleos/pull/5).
