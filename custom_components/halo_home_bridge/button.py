"""Read device state through the bridge."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .entity import HaloControl, discover_controls


async def async_setup_entry(hass, entry, async_add_entities):
    def factory(coordinator, pid, record):
        yield "refresh", HaloButton(coordinator, pid)
    discover_controls(entry, async_add_entities, factory)


class HaloButton(HaloControl, ButtonEntity):
    def __init__(self, coordinator, pid):
        super().__init__(coordinator, pid, "refresh")
        self._attr_name = "Refresh state"
        self._attr_icon = "mdi:refresh"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self):
        await self.coordinator.async_request_refresh()
