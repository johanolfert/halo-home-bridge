"""HALO light entities backed exclusively by the internet bridge."""
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN, ColorMode, LightEntity,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import lamp_features
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def discover():
        new = set(coordinator.data) - known
        if new:
            async_add_entities(HaloLight(coordinator, pid) for pid in sorted(new))
            known.update(new)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class HaloLight(CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 5000

    def __init__(self, coordinator, pid):
        super().__init__(coordinator)
        self.pid = pid
        device = coordinator.data[pid]["device"]
        features = lamp_features(device)
        self._features = features
        if "_cct_range" in device:
            self._attr_min_color_temp_kelvin, self._attr_max_color_temp_kelvin = device["_cct_range"]
        mode = (ColorMode.COLOR_TEMP if "WHITE" in features else
                ColorMode.BRIGHTNESS if "DIM" in features else ColorMode.ONOFF)
        self._attr_supported_color_modes = {mode}
        self._attr_color_mode = mode
        self._attr_unique_id = f"{coordinator.entry.data['location_id']}:{pid}"
        product = device.get("product") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=device.get("name") or f"HALO {pid}",
            manufacturer="HALO Home / Avi-on",
            model=product.get("name", "HALO lamp"),
            sw_version=device.get("current_version"),
        )

    @property
    def record(self):
        return self.coordinator.data.get(self.pid, {})

    @property
    def available(self):
        return super().available and self.record.get("available", False)

    @property
    def is_on(self):
        return self.record.get("state", {}).get("on")

    @property
    def brightness(self):
        return self.record.get("state", {}).get("brightness")

    @property
    def color_temp_kelvin(self):
        return self.record.get("state", {}).get("kelvin")

    @property
    def extra_state_attributes(self):
        return {"connection": "Avi-on cloud → HALO bridge", "location_id":
                self.coordinator.entry.data["location_id"], **self.coordinator.tracker.attributes(self.pid)}

    async def _send(self, commands):
        device = self.record["device"]
        await self.coordinator.send(device["pid"], commands, device.get("_kind", "devices"))

    async def async_turn_on(self, **kwargs):
        if kwargs.get(ATTR_BRIGHTNESS) == 0:
            await self.async_turn_off()
            return
        commands = []
        # HALO's on command can restore its previous/default brightness. Send it
        # before explicit settings, and avoid re-sending it to an already-on lamp.
        if "ON_OFF" in self._features and self.is_on is not True:
            commands.append(("on_off", "on"))
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = max(self.min_color_temp_kelvin,
                         min(self.max_color_temp_kelvin, int(kwargs[ATTR_COLOR_TEMP_KELVIN])))
            commands.append(("white", str(kelvin)))
        if ATTR_BRIGHTNESS in kwargs:
            percent = max(1, min(100, round(int(kwargs[ATTR_BRIGHTNESS]) * 100 / 255)))
            commands.append(("dim", f"{percent}%"))
        if "ON_OFF" not in self._features and ATTR_BRIGHTNESS not in kwargs:
            commands.append(("dim", f"{max(1, round((self.brightness or 255) * 100 / 255))}%"))
        await self._send(commands)

    async def async_turn_off(self, **kwargs):
        await self._send([("on_off", "off")] if "ON_OFF" in self._features else [("dim", "0%")])
