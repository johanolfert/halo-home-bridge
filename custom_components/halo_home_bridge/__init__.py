"""HALO Home through its existing cloud-connected bridge."""
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from pathlib import Path

from .api import HaloApi
from .coordinator import HaloCoordinator
from .const import DOMAIN

PLATFORMS = [Platform.LIGHT, Platform.SELECT, Platform.NUMBER, Platform.SCENE, Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass, entry):
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("frontend_registered"):
        await hass.http.async_register_static_paths([StaticPathConfig(
            "/halo_home_bridge/frontend", str(Path(__file__).parent / "frontend"), False
        )])
        frontend.add_extra_js_url(hass, "/halo_home_bridge/frontend/halo-filter.js?v=0.2.4")
        data["frontend_registered"] = True
    # Remove only this integration's retired per-device Configuration entities.
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.endswith((":default_brightness", ":default_kelvin", ":reset_defaults")):
            registry.async_remove(entity.entity_id)
    if "device_defaults" in entry.options:
        hass.config_entries.async_update_entry(entry, options={
            key: value for key, value in entry.options.items() if key != "device_defaults"
        })
    def persist(credentials):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "credentials": credentials}
        )

    api = HaloApi(async_get_clientsession(hass), entry.data["credentials"], persist)
    coordinator = HaloCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass, entry):
    coordinator = entry.runtime_data
    from datetime import timedelta
    coordinator.update_interval = timedelta(seconds=entry.options.get("poll_seconds", 60))


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

