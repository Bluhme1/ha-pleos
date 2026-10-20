# Supported vehicles

[Back to setup guide](../README.md)

**Tested and working with a Kia PV5 Passenger.** Available fields depend on the data returned by the vehicle's API.

Pleos documents access to European vehicles using **Hyundai Bluelink, Kia Connect or Genesis Connected services**. See the [official supported-country list](https://document.pleos.ai/en/api-reference/vehicle-data-api/faq).

The following models and variant labels appear in the [Vehicle Data API compatibility matrix](https://document.pleos.ai/en/api-reference/vehicle-data-api/api-compatibility), checked **12 October 2026**:

| Manufacturer | Documented models and variants |
| --- | --- |
| Hyundai | ELANTRA (NORMAL); INSTER (EV); IONIQ 5 (EV); IONIQ 6 (EV); IONIQ (EV, HEV, PHEV); KONA Electric (HEV); KONA N (NORMAL); KONA (EV, HEV, NORMAL); NEXO (FCEV); SANTA FE (HEV, NORMAL, PHEV); STARIA (HEV, NORMAL); TUCSON (HEV, NORMAL, PHEV); i10 (NORMAL); i20 / BAYON (NORMAL); i20 N (NORMAL); i30 N (NORMAL); i30 (NORMAL) |
| Kia | CEED (NORMAL, PHEV); EV3 (EV); EV6 (EV); EV9 (EV); NIRO (EV, HEV, PHEV); Picanto (NORMAL); SORENTO (HEV, NORMAL, PHEV); SOUL EV (EV); SPORTAGE (HEV, NORMAL, PHEV); STINGER (NORMAL); STONIC (NORMAL) |
| Genesis | G70 (NORMAL); G80 (EV, NORMAL); G90 (NORMAL); GV60 (EV); GV70 (EV, NORMAL); GV80 (NORMAL) |

These are Pleos's labels, including “KONA Electric (HEV)”; the matrix does not specify model years. The integration discovers cars through [Get Vehicles](https://document.pleos.ai/en/api-reference/vehicle-data-api/vehicle-data-api/for-private-users/get-vehicles), so other models may work too. Available fields vary by vehicle.
