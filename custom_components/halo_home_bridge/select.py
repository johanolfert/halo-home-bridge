"""Color temperature presets derived from lamp limits."""
from homeassistant.components.select import SelectEntity
from .api import lamp_features
from .entity import HaloControl, discover_controls
from .presets import current_preset, supported_presets


async def async_setup_entry(hass, entry, async_add_entities):
    def factory(coordinator, pid, record):
        if "WHITE" in lamp_features(record["device"]):
            yield "cct_preset", HaloCctPreset(coordinator, pid)
    discover_controls(entry, async_add_entities, factory)


class HaloCctPreset(HaloControl, SelectEntity):
    _attr_name = "CCT preset"
    _attr_icon = "mdi:palette-outline"

    def __init__(self, coordinator, pid):
        super().__init__(coordinator, pid, "cct_preset")
        low, high = self.record["device"].get("_cct_range", (2700, 5000))
        self.presets = supported_presets(low, high)
        self._attr_options = [*self.presets, "Custom"]

    @property
    def current_option(self):
        return current_preset(self.record.get("state", {}).get("kelvin"), self.presets)

    async def async_select_option(self, option):
        if option == "Custom":
            return  # Use the CCT number entity to set a custom value.
        await self.send("white", str(self.presets[option]))
