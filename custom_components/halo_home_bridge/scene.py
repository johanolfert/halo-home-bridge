"""Activate existing HALO scenes through the bridge."""
from homeassistant.components.scene import Scene
from homeassistant.helpers.update_coordinator import CoordinatorEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()
    def discover():
        entities = []
        for scene in coordinator.scenes:
            pid = str(scene.get("pid", ""))
            if pid and pid not in known:
                known.add(pid)
                entities.append(HaloScene(coordinator, scene))
        if entities:
            async_add_entities(entities)
    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class HaloScene(CoordinatorEntity, Scene):
    _attr_icon = "mdi:movie-open-outline"

    def __init__(self, coordinator, scene):
        super().__init__(coordinator)
        self.pid = str(scene["pid"])
        self._attr_name = f"HALO {scene.get('name', 'Scene')}"
        self._attr_unique_id = f"{coordinator.entry.data['location_id']}:scene:{self.pid}"

    @property
    def available(self):
        return super().available and self.coordinator.catalog_available and any(
            str(s.get("pid")) == self.pid for s in self.coordinator.scenes)

    async def async_activate(self, **kwargs):
        await self.coordinator.send(self.pid, [("action", "on")], "scenes")
