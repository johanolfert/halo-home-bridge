"""Shared lamp controls and discovery."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def discover_controls(entry, async_add_entities, factory):
    coordinator = entry.runtime_data
    known = set()
    def discover():
        entities = []
        for pid, record in coordinator.data.items():
            for suffix, entity in factory(coordinator, pid, record):
                key = (pid, suffix)
                if key not in known:
                    known.add(key)
                    entities.append(entity)
        if entities:
            async_add_entities(entities)
    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class HaloControl(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, pid, suffix):
        super().__init__(coordinator)
        self.pid = pid
        base_id = f"{coordinator.entry.data['location_id']}:{pid}"
        self._attr_unique_id = f"{base_id}:{suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, base_id)})

    @property
    def record(self):
        return self.coordinator.data.get(self.pid, {})

    @property
    def available(self):
        return super().available and self.record.get("available", False)

    async def send(self, feature, value):
        device = self.record["device"]
        await self.coordinator.send(device["pid"], [(feature, value)], device.get("_kind", "devices"))

    @property
    def extra_state_attributes(self):
        return self.coordinator.tracker.attributes(self.pid)

