"""Live lamp brightness and color-temperature sliders."""
from homeassistant.components.number import NumberEntity, NumberMode
from .api import lamp_features
from .entity import HaloControl, discover_controls
from .presets import validate_setting


async def async_setup_entry(hass, entry, async_add_entities):
    def factory(coordinator, pid, record):
        features = lamp_features(record["device"])
        for feature, key, name, unit in [("WHITE", "kelvin", "Color temperature", "K"),
                                         ("DIM", "brightness", "Brightness", "%")]:
            if feature in features:
                yield key, HaloNumber(coordinator, pid, key, name, unit)
    discover_controls(entry, async_add_entities, factory)


class HaloNumber(HaloControl, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, coordinator, pid, key, name, unit):
        super().__init__(coordinator, pid, key)
        self.key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = "mdi:thermometer" if key == "kelvin" else "mdi:brightness-6"
        if key == "kelvin":
            self._attr_native_min_value, self._attr_native_max_value = self.record["device"].get("_cct_range", (2700, 5000))
        else:
            self._attr_native_min_value, self._attr_native_max_value = 0, 100

    @property
    def native_value(self):
        value = self.record.get("state", {}).get(self.key)
        return round(value * 100 / 255) if value is not None and self.key == "brightness" else value

    async def async_set_native_value(self, value):
        value = validate_setting(value, self.native_min_value, self.native_max_value)
        await self.send("white" if self.key == "kelvin" else "dim", str(value) if self.key == "kelvin" else f"{value}%")
