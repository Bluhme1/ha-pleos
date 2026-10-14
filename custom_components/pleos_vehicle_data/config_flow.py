"""Guided setup and replacement of manually renewed personal API keys."""

import probatio as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector, NumberSelector, NumberSelectorConfig, NumberSelectorMode,
    SelectSelector, SelectSelectorConfig, SelectSelectorMode,
    TextSelector, TextSelectorConfig, TextSelectorType,
)

from .api import ApiError, AuthError, PleosClient
from .const import BRANDS, DEFAULT_OPTIONS, DOMAIN

KEY_FIELDS = {
    vol.Required("client_id"): TextSelector(),
    vol.Required("client_secret"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
}
PLEOS_URL = "https://pleos.ai/"
KEY_GUIDE_URL = "https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/request-my-vehicle-api-key"


class PleosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def validate(self, brand, user_input):
        credentials = {key: user_input[key].strip() for key in ("client_id", "client_secret")}
        if not all(credentials.values()):
            return "invalid_auth"
        try:
            await PleosClient(async_get_clientsession(self.hass), brand, **credentials).vehicles()
        except AuthError:
            return "invalid_auth"
        except ApiError as error:
            return "rate_limited" if error.status == 429 else "cannot_connect"
        return None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            brand = user_input["brand"]
            await self.async_set_unique_id(brand)
            self._abort_if_unique_id_configured()
            if error := await self.validate(brand, user_input):
                errors["base"] = error
            else:
                data = {key: value.strip() for key, value in user_input.items()}
                return self.async_create_entry(title=BRANDS[brand], data=data)
        schema = vol.Schema({
            vol.Required("brand"): SelectSelector(SelectSelectorConfig(
                options=[{"value": key, "label": name} for key, name in BRANDS.items()],
                mode=SelectSelectorMode.DROPDOWN,
            )), **KEY_FIELDS,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors,
                                    description_placeholders={"pleos_url": PLEOS_URL, "key_guide_url": KEY_GUIDE_URL})

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self.replace_key("reauth_confirm", self._get_reauth_entry(), user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self.replace_key("reconfigure", self._get_reconfigure_entry(), user_input)

    async def replace_key(self, step, entry, user_input):
        errors = {}
        if user_input:
            if error := await self.validate(entry.data["brand"], user_input):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={key: user_input[key].strip() for key in ("client_id", "client_secret")},
                )
        return self.async_show_form(step_id=step, data_schema=vol.Schema(KEY_FIELDS), errors=errors,
                                    description_placeholders={"brand": BRANDS[entry.data["brand"]], "pleos_url": PLEOS_URL})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PleosOptionsFlow()


class PleosOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = DEFAULT_OPTIONS | dict(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("poll_minutes", default=options["poll_minutes"]): NumberSelector(
                NumberSelectorConfig(min=5, max=1440, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="min")),
            vol.Required("stale_minutes", default=options["stale_minutes"]): NumberSelector(
                NumberSelectorConfig(min=5, max=10080, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="min")),
            vol.Required("location", default=options["location"]): BooleanSelector(),
            vol.Required("trip_events", default=options["trip_events"]): BooleanSelector(),
        }))
