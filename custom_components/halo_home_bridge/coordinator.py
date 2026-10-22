"""Poll cloud state without allowing Bluetooth fallback."""
import asyncio
from datetime import timedelta
import logging
import time

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthenticationError, is_lamp
from .const import POLL_SECONDS
from .state_tracking import StateTracker

_LOGGER = logging.getLogger(__name__)


class HaloCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(hass, _LOGGER, name="HALO Home Bridge", config_entry=entry,
                         update_interval=timedelta(seconds=POLL_SECONDS))
        self.api = api
        self.entry = entry
        self.command_lock = asyncio.Lock()
        self.scenes = []
        self.schedules = []
        self.catalog_available = False
        self.bridges = []
        self.bridge_status_available = False
        self._groups = []
        self._location_pid = None
        self._catalog_at = 0
        self.tracker = StateTracker()
        self._verification_task = None
        self._verification_keys = set()
        entry.async_on_unload(self._cancel_verification)
        self.update_interval = timedelta(seconds=entry.options.get("poll_seconds", POLL_SECONDS))

    async def send(self, pid, commands, kind="devices"):
        from homeassistant.exceptions import HomeAssistantError
        try:
            async with self.command_lock:
                for feature, value in commands:
                    await self.api.set_feature(pid, feature, value, kind)
                    key = f"group:{pid}" if kind == "groups" else str(pid)
                    keys = [key]
                    if kind == "groups":
                        keys.extend(str(member) for member in self.data.get(key, {}).get("device", {}).get("devices", []))
                    if kind in {"devices", "groups"}:
                        for target in keys:
                            self.tracker.accept(target, feature, value)
                        self._verification_keys.update(keys)
                        self._publish_pending()
                        self._start_verification()
        except AuthenticationError as err:
            self.entry.async_start_reauth(self.hass)
            raise HomeAssistantError(str(err)) from err
        except ApiError as err:
            raise HomeAssistantError(str(err)) from err
        if kind == "scenes":
            await self.async_request_refresh()

    def _cancel_verification(self):
        if self._verification_task:
            self._verification_task.cancel()

    def _start_verification(self):
        if self._verification_task is None or self._verification_task.done():
            self._verification_task = self.hass.async_create_task(self._verify_commands())

    def _publish_pending(self):
        self.async_set_updated_data(self._apply_pending(self.data))

    def _apply_pending(self, records):
        updated = {}
        for key, record in records.items():
            state = self.tracker.reconcile(key, record.get("cloud_state", record["state"]), record["device"].get("_state_versions"))
            updated[key] = {**record, "state": state}
        return updated

    async def _verify_commands(self):
        # Targeted reads avoid polling every room repeatedly after each command.
        try:
            delay = 1
            while self._verification_keys:
                await asyncio.sleep(delay)
                keys = set(self._verification_keys)
                updates = {}
                semaphore = asyncio.Semaphore(4)
                async def fetch(key):
                    record = self.data.get(key)
                    if record is None:
                        self.tracker.fail(key)
                        return
                    device = dict(record["device"])
                    async with semaphore:
                        started = time.monotonic()
                        try:
                            raw = await self.api.state(device["pid"], device, device.get("_kind", "devices"))
                            state = self.tracker.reconcile(key, raw, device.get("_state_versions"), started)
                            updates[key] = {**record, "device": device, "state": state, "cloud_state": raw,
                                            "available": device.get("reachable") is not False}
                        except AuthenticationError:
                            self.entry.async_start_reauth(self.hass)
                            self.tracker.fail(key)
                            updates[key] = {**record, "state": record.get("cloud_state", {}), "available": False}
                        except ApiError:
                            # Expire pending estimates even if the cloud stops responding.
                            state = self.tracker.reconcile(key, record.get("cloud_state", record["state"]), read_started=None)
                            updates[key] = {**record, "state": state, "available": False}
                await asyncio.gather(*(fetch(key) for key in keys))
                if updates:
                    # A newer command may arrive while another target's read awaits.
                    self.async_set_updated_data(self._apply_pending({**self.data, **updates}))
                self._verification_keys = {key for key in self._verification_keys if self.tracker.has_pending({key})}
                delay = min(delay * 2, 8)
        finally:
            self._verification_task = None

    async def _async_update_data(self):
        try:
            devices = await self.api.devices()
            try:
                if self._location_pid is None:
                    self._location_pid = await self.api.location_pid(self.entry.data["location_id"])
                self.bridges = await self.api.bridges(self._location_pid)
                self.bridge_status_available = True
            except AuthenticationError:
                raise
            except ApiError:
                self.bridge_status_available = False
            selected = [d for d in devices if is_lamp(d)
                        and str(d.get("location_id")) == self.entry.data["location_id"]]
            if time.monotonic() - self._catalog_at > 300 or not self.catalog_available:
                try:
                    if self._location_pid is None:
                        self._location_pid = await self.api.location_pid(self.entry.data["location_id"])
                    groups, scenes, schedules = await asyncio.gather(*(
                        self.api.catalog(self._location_pid, kind)
                        for kind in ("groups", "scenes", "schedules")))
                    self._groups, self.scenes, self.schedules = groups, scenes, schedules
                    self.catalog_available = True
                    self._catalog_at = time.monotonic()
                except AuthenticationError:
                    raise
                except ApiError:
                    self.catalog_available = False
                    _LOGGER.debug("HALO groups/scenes/schedules could not be refreshed")
            for group in self._groups:
                selected.append({**group, "_kind": "groups", "product": {"name": "HALO group"}})
            semaphore = asyncio.Semaphore(4)

            async def fetch(device):
                async with semaphore:
                    try:
                        kind = device.get("_kind", "devices")
                        started = time.monotonic()
                        state = await self.api.state(device["pid"], device, kind)
                        key = f"group:{device['pid']}" if kind == "groups" else str(device["pid"])
                        raw_state = dict(state)
                        state = self.tracker.reconcile(key, state, device.get("_state_versions"), started)
                        return key, {"device": device, "state": state, "cloud_state": raw_state,
                            "available": device.get("reachable") is not False}
                    except AuthenticationError:
                        raise
                    except ApiError:
                        key = f"group:{device['pid']}" if device.get("_kind") == "groups" else str(device["pid"])
                        return key, {"device": device, "state": {}, "available": False}

            return self._apply_pending(dict(await asyncio.gather(*(fetch(d) for d in selected))))
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
