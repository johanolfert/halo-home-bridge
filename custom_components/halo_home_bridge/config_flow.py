"""Sign in and select the mesh location connected to the HALO bridge."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import ApiError, AuthenticationError, HaloApi, is_lamp
from .const import DOMAIN


class HaloConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return HaloOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            email = user_input[CONF_EMAIL].strip().lower()
            api = HaloApi(async_get_clientsession(self.hass))
            try:
                await api.login(email, user_input[CONF_PASSWORD])
                devices = await api.devices()
                locations = sorted({str(d["location_id"]) for d in devices
                                    if is_lamp(d) and d.get("location_id") is not None})
                if not locations:
                    errors["base"] = "no_lights"
                else:
                    self._email = email
                    self._credentials = api.credentials
                    self._locations = locations
                    return await self.async_step_location()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }), errors=errors)


    async def async_step_location(self, user_input=None):
        if user_input is None and len(self._locations) == 1:
            user_input = {"location_id": self._locations[0]}
        if user_input:
            location = user_input["location_id"]
            await self.async_set_unique_id(f"{self._email}:{location}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"HALO Home Bridge ({location})", data={
                "email": self._email, "credentials": self._credentials,
                "location_id": location,
            })
        return self.async_show_form(step_id="location", data_schema=vol.Schema({
            vol.Required("location_id", default=self._locations[0]): vol.In(self._locations),
        }))

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input:
            entry = self._get_reauth_entry()
            api = HaloApi(async_get_clientsession(self.hass))
            try:
                await api.login(entry.data["email"], user_input[CONF_PASSWORD])
                return self.async_update_reload_and_abort(entry, data_updates={
                    "credentials": api.credentials,
                })
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }), errors=errors)


class HaloOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("poll_seconds", default=self.config_entry.options.get("poll_seconds", 60)):
                vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
        }))
