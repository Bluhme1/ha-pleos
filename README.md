# Pleos Vehicle Data

A native Home Assistant integration for the official Pleos **personal Vehicle Data API**. Supports Hyundai, Kia and Genesis accounts, with one integration entry per manufacturer and a device for each returned vehicle. Requires Home Assistant **2026.10 or later**.

## Supported vehicles

**Tested and working with a Kia PV5 Passenger.** Available fields depend on the data returned by the vehicle's API.

Pleos documents access to European vehicles using **Hyundai Bluelink, Kia Connect or Genesis Connected services**. See the [official supported-country list](https://document.pleos.ai/en/api-reference/vehicle-data-api/faq).

The following models and variant labels appear in the [Vehicle Data API compatibility matrix](https://document.pleos.ai/en/api-reference/vehicle-data-api/api-compatibility), checked **12 October 2026**:

| Manufacturer | Documented models and variants |
| --- | --- |
| Hyundai | ELANTRA (NORMAL); INSTER (EV); IONIQ 5 (EV); IONIQ 6 (EV); IONIQ (EV, HEV, PHEV); KONA Electric (HEV); KONA N (NORMAL); KONA (EV, HEV, NORMAL); NEXO (FCEV); SANTA FE (HEV, NORMAL, PHEV); STARIA (HEV, NORMAL); TUCSON (HEV, NORMAL, PHEV); i10 (NORMAL); i20 / BAYON (NORMAL); i20 N (NORMAL); i30 N (NORMAL); i30 (NORMAL) |
| Kia | CEED (NORMAL, PHEV); EV3 (EV); EV6 (EV); EV9 (EV); NIRO (EV, HEV, PHEV); Picanto (NORMAL); SORENTO (HEV, NORMAL, PHEV); SOUL EV (EV); SPORTAGE (HEV, NORMAL, PHEV); STINGER (NORMAL); STONIC (NORMAL) |
| Genesis | G70 (NORMAL); G80 (EV, NORMAL); G90 (NORMAL); GV60 (EV); GV70 (EV, NORMAL); GV80 (NORMAL) |

These are the matrix's labels, including “KONA Electric (HEV)”. Pleos does not specify model years in that table. A listing does not guarantee every field. The integration discovers cars through [Get Vehicles](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/for-private-users/get-vehicles); it does not restrict setup to this list.

## Data available in Home Assistant

All ten common Vehicle Data API endpoints are queried. Fields appear when the API supplies valid values for the vehicle.

| API | Endpoint suffix | Exposed data |
| --- | --- | --- |
| [Battery charging](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-battery-charging-status) | `batteries` | Plug connection, charging state, charge percentage, capacity, charge targets and remaining charge time |
| [Powertrain status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-powertrain-status) | `powertrains` | Fuel level, battery percentage and remaining range |
| [Location](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-location-info) | `locations` | Coordinates, altitude, heading and speed; GPS tracker for valid WGS84 coordinates |
| [Driving status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-operation-status) | `driving` | Ignition, power states, sleep mode, odometer and parking position |
| [Vehicle status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-status) | `status` | Doors, bonnet, boot, sunroof, tyres, warnings, climate, defrost, steering-wheel heat, seats and outside temperature |
| [Freezer status](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-freezer-status) | `freezer` | Operation state and temperature |
| [Powertrain trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-powertrain-data) | `powertrains/data` | Battery voltage, engine oil temperature and RPM samples |
| [Speed trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-speed-data) | `speed` | Dashboard speed, units and four wheel-speed series |
| [Driving trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-operation-data) | `driving/data` | Ignition, mileage, acceleration, yaw, ISLA settings, seat belts, steering and gear samples |
| [Vehicle status trips](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/common/get-vehicle-data) | `status/data` | Door, lamp, tyre-pressure, low-fuel-warning and outside-temperature samples |

Each endpoint has an **API diagnostic sensor** showing `available`, `no_data`, `error` or `disabled`. Its `data` attribute contains the complete returned vehicle payload, including arrays and fields without a dedicated sensor; response metadata is under `api_metadata`. Vehicle information includes VIN, nickname, model code, model name and powertrain type.

Trip queries cover **yesterday and today in UTC**. Full returned trips remain in the diagnostic sensor's `data` attribute. Individual trip sensors show the latest trip's final sample when valid, with trip start, duration and sample index. Invalid final samples are omitted rather than replaced by older readings. Pleos does not document individual sample timestamps, so none are invented. Trip readings are historical and do not use the current-status freshness cutoff.

Snapshot endpoints have reporting-time and data-age sensors when a valid vehicle timestamp is supplied. The location option disables both the location request and GPS tracking.

## Install with HACS

1. [Install and configure HACS](https://www.hacs.dev/docs/use/download/download/) if required.
2. Open **HACS → ⋮ → Custom repositories**. Add `https://github.com/jouwdan/ha-pleos` with type **Integration**.
3. Find **Pleos Vehicle Data**, download it, then restart Home Assistant.
4. Complete the setup below. HACS manages later integration downloads and updates.

## Install without HACS

1. Download the source ZIP from the [latest release](https://github.com/jouwdan/ha-pleos/releases/latest).
2. Extract it and copy `custom_components/pleos_vehicle_data` into your Home Assistant configuration directory's `custom_components` folder. The result must be `<config>/custom_components/pleos_vehicle_data/manifest.json`.
3. Restart Home Assistant and complete the setup below. For updates, replace that integration directory with the new release and restart.

## Set up your account

1. Sign into [Pleos Playground](https://pleos.ai/). Open the account menu → **My Vehicle Data API**. This menu is available to users in Europe.
2. Select the manufacturer, accept the required terms, choose **Get API Key**, and sign into the manufacturer's account. Copy **Client ID** and **Client Secret**. Private users do not need a business project or API-access approval. [Official key-generation guide](https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/request-my-vehicle-api-key).
3. In Home Assistant, open **Settings → Devices & services → Add integration → Pleos Vehicle Data**. Select that manufacturer and enter both credentials. Setup validates them before saving.
4. Add the car's entities to dashboards or automations. Repeat setup for another manufacturer if needed.

## Expired or replaced API keys

Personal keys expire and require **manual renewal**. Check the expiry shown in Pleos. The integration renews access tokens automatically, not the personal key. [Official key-management guide](https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/manage-my-vehicle-api-key).

When credentials are rejected, polling stops and Home Assistant requests reauthentication. Generate a new personal key and replace **both Client ID and Client Secret** in that request. To replace credentials before expiry, use the manufacturer's **⋮ → Reconfigure** menu. The existing entry reloads and retains entity IDs for the same vehicles.

Pleos invalidates old access tokens when a key expires, is revoked or is reissued. A newly registered or activated vehicle also needs a new key: vehicle access is fixed at issuance. [Get Vehicles rules](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/for-private-users/get-vehicles).

## Limitations and privacy

- Default polling is **15 minutes**; snapshot readings older than **60 minutes** become unavailable. Both settings are configurable, and freshness is checked at each poll.
- Availability varies with vehicle, powertrain, model year, region and connected-service settings. Null or documented invalid values do not become vehicle readings. `no_data` is an API result, not a guarantee of future availability. [Pleos FAQ](https://document.pleos.ai/en/api-reference/vehicle-data-api/faq).
- This is a read-only cloud integration. It does not implement remote vehicle commands, camera access, the in-car SDK, Fleet API or business-user authentication/consent flows. Status snapshots and returned trip samples are not live telemetry.
- A failing optional endpoint does not hide other endpoint data. Network errors and rate limits retry automatically; `Retry-After` is respected. Responses above **16 MiB** are rejected.
- Keys live in Home Assistant's private configuration; access tokens stay in memory. Credentials and VINs are not logged. Raw payloads and VIN attributes are excluded from recorder history, but remain accessible in current entity attributes. Protect configuration files and backups.
