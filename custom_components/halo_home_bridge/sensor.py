"""Read-only visibility of schedules stored in the HALO mesh."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .entity import HaloControl, discover_controls


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([HaloBridgeStatus(coordinator)])
    def factory(coordinator, pid, record):
        if record["device"].get("_kind", "devices") == "devices":
            yield "firmware", HaloFirmware(coordinator, pid)
            yield "time_sync", HaloTimeSync(coordinator, pid)
    discover_controls(entry, async_add_entities, factory)
    known = set()
    def discover():
        entities = []
        for schedule in coordinator.schedules:
            avid = schedule.get("avid")
            if avid is not None and str(avid) not in known:
                known.add(str(avid))
                entities.append(HaloSchedule(coordinator, schedule))
        if entities:
            async_add_entities(entities)
    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class HaloBridgeStatus(CoordinatorEntity, SensorEntity):
    _attr_name = "HALO bridge connection"
    _attr_icon = "mdi:router-wireless"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.data['location_id']}:bridge_connection"

    @property
    def available(self):
        return super().available and self.coordinator.bridge_status_available

    @property
    def native_value(self):
        statuses = [str(b.get("remote_status", "")).lower() for b in self.coordinator.bridges]
        if "online" in statuses:
            return "Online"
        if statuses and all(s in {"offline", "not_configured"} for s in statuses):
            return "Offline"
        return "Unknown"

    @property
    def extra_state_attributes(self):
        return {"halo_bridge_status": True, "location_id": self.coordinator.entry.data["location_id"],
                "source": "Avi-on bridge remote_status", "bridges": self.coordinator.bridges}


class HaloFirmware(HaloControl, SensorEntity):
    _attr_name = "Firmware version"
    _attr_icon = "mdi:chip"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, pid):
        super().__init__(coordinator, pid, "firmware")

    @property
    def native_value(self):
        return self.record.get("device", {}).get("current_version")


class HaloTimeSync(HaloControl, SensorEntity):
    _attr_name = "Date and time sync"
    _attr_icon = "mdi:clock-sync"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, pid):
        super().__init__(coordinator, pid, "time_sync")

    @property
    def native_value(self):
        return "Use HALO Home app"

    @property
    def extra_state_attributes(self):
        return {**self.record.get("device", {}).get("_clock_info", {}),
            "manual_bridge_sync_supported": False,
            "reason": "Manual clock synchronization is not exposed by the public bridge API.",
            "clock_source": "Cloud-reported snapshot; not a live clock or proof of sync",
        }


class HaloSchedule(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, schedule):
        super().__init__(coordinator)
        self.avid = str(schedule["avid"])
        self._attr_name = f"HALO schedule {schedule.get('name', self.avid)}"
        self._attr_unique_id = f"{coordinator.entry.data['location_id']}:schedule:{self.avid}"

    @property
    def schedule(self):
        return next((s for s in self.coordinator.schedules if str(s.get("avid")) == self.avid), None)

    @property
    def available(self):
        return super().available and self.coordinator.catalog_available and self.schedule is not None

    @property
    def native_value(self):
        schedule = self.schedule or {}
        return "Enabled" if schedule.get("active") else "Disabled"

    @property
    def extra_state_attributes(self):
        schedule = self.schedule or {}
        return {k: schedule[k] for k in ("name", "days", "mode", "start", "dim") if k in schedule} | {
            "editable_in": "HALO Home app", "execution": "Existing HALO mesh schedule"}
