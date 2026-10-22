"""Avi-on public cloud API. No Bluetooth or direct LAN transport."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import API_ACCEPT, API_URL


class ApiError(Exception):
    """Cloud request failed (never includes response bodies or credentials)."""


class AuthenticationError(ApiError):
    """Account must sign in again."""


class HaloApi:
    def __init__(self, session, credentials=None, credentials_updated=None):
        self.session = session
        self.credentials = dict(credentials or {})
        self.credentials_updated = credentials_updated
        self._auth_lock = asyncio.Lock()

    async def _raw(self, method, path, *, authorization=None, body=None, version=2):
        headers = {"Accept": API_ACCEPT if version == 2 else "application/vnd.avi-on.v3+json", "Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        try:
            async with self.session.request(
                method, f"{API_URL}/{path}", headers=headers, json=body,
                timeout=aiohttp.ClientTimeout(total=20), allow_redirects=False,
            ) as response:
                if response.status == 401:
                    raise AuthenticationError("Sign in to HALO Home again")
                if response.status >= 300:
                    raise ApiError(f"Avi-on returned HTTP {response.status}")
                data = await response.json()
                if not isinstance(data, dict):
                    raise ApiError("Unexpected Avi-on response")
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ApiError("Cannot read Avi-on cloud response") from err

    def _set_credentials(self, data):
        value = data.get("credentials")
        if not isinstance(value, dict) or not value.get("auth_token"):
            raise ApiError("Avi-on did not return a session token")
        self.credentials = {
            key: value[key] for key in ("auth_token", "refresh_token", "expiration_date")
            if key in value
        }
        if self.credentials_updated:
            self.credentials_updated(dict(self.credentials))

    async def login(self, email, password):
        self._set_credentials(await self._raw(
            "POST", "sessions", body={"email": email, "password": password}
        ))

    async def request(self, method, path, body=None, version=2):
        token = self.credentials.get("auth_token")
        if not token:
            raise AuthenticationError("Missing session token")
        try:
            return await self._raw(method, path, authorization=f"Token {token}", body=body, version=version)
        except AuthenticationError:
            async with self._auth_lock:
                if self.credentials.get("auth_token") == token:
                    refresh = self.credentials.get("refresh_token")
                    if not refresh:
                        raise AuthenticationError("Missing refresh token")
                    self._set_credentials(await self._raw(
                        "PUT", "sessions", authorization=f"RefreshToken {refresh}"
                    ))
            return await self._raw(
                method, path, authorization=f"Token {self.credentials['auth_token']}", body=body, version=version
            )

    async def devices(self):
        data = await self.request("GET", "user/devices")
        devices = data.get("devices")
        if not isinstance(devices, list):
            raise ApiError("Avi-on device list has an unexpected format")
        return [d for d in devices if isinstance(d, dict)]

    async def state(self, pid, device=None, kind="devices"):
        if kind not in {"devices", "groups"}:
            raise ValueError("Unsupported state target")
        data = await self.request("GET", f"{kind}/{quote(str(pid), safe='')}/state")
        rows = data.get("state")
        if not isinstance(rows, list):
            raise ApiError("Avi-on state has an unexpected format")
        if device is not None:
            enrich_device(device, rows)
        return parse_state(rows)

    async def set_feature(self, pid, feature, value, kind="devices"):
        if kind not in {"devices", "groups", "scenes"}:
            raise ValueError("Unsupported command target")
        if kind == "scenes" and feature != "action":
            raise ValueError("Scenes only support activation")
        if feature not in {"on_off", "dim", "white"} and not (kind == "scenes" and feature == "action"):
            raise ValueError("Unsupported lamp feature")
        return await self.request(
            "POST", f"{kind}/{quote(str(pid), safe='')}/state",
            {"state": {"feature": feature, "value": str(value)}},
        )

    async def location_pid(self, location_id):
        data = await self.request("GET", "user/locations", version=3)
        for stub in data.get("locations", []):
            pid = stub.get("pid")
            if pid is None:
                continue
            detail = await self.request("GET", f"locations/{quote(str(pid), safe='')}", version=3)
            if str(detail.get("location", {}).get("id")) == str(location_id):
                return str(pid)
        raise ApiError("Selected HALO location was not found")

    async def catalog(self, location_pid, collection):
        if collection not in {"groups", "scenes", "schedules"}:
            raise ValueError("Unsupported catalog")
        data = await self.request("GET", f"locations/{quote(str(location_pid), safe='')}/{collection}", version=3)
        rows = data.get(collection)
        if not isinstance(rows, list):
            raise ApiError("Unexpected HALO catalog format")
        return [row for row in rows if isinstance(row, dict)]

    async def bridges(self, location_pid):
        data = await self.request("GET", f"locations/{quote(str(location_pid), safe='')}/rabs", version=3)
        rows = data.get("rabs")
        if not isinstance(rows, list):
            raise ApiError("Unexpected HALO bridge status format")
        return [{key: row.get(key) for key in ("pid", "name", "remote_status", "status_updated_at")}
                for row in rows if isinstance(row, dict)]


def lamp_features(device: dict[str, Any]) -> set[str]:
    if "_state_features" in device:
        return set(device["_state_features"])
    product = device.get("product") or {}
    features = product.get("features", []) if isinstance(product, dict) else []
    return {str(feature).upper() for feature in features}


def is_lamp(device):
    product = device.get("product") or {}
    category = product.get("category", "") if isinstance(product, dict) else ""
    return (device.get("type", "device") == "device" and bool(device.get("pid"))
            and (str(category).upper() == "LIGHT"
                 or bool(lamp_features(device) & {"ON_OFF", "DIM", "WHITE"})))


def enrich_device(device, rows):
    """Current HALO products publish capabilities on the state endpoint."""
    features = set()
    device["_state_versions"] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("name", "")).lower() == "clock":
            device["_clock_info"] = {
                "reported_clock": row.get("humanized"),
                "reported_at": row.get("updated_at"),
                "writable": row.get("write") is True,
            }
        field = {"white": "kelvin", "dim": "brightness", "on_off": "on"}.get(str(row.get("name", "")).lower())
        if field:
            device["_state_versions"][field] = row.get("updated_at")
        if row.get("write") is False:
            continue
        feature = str(row.get("name", "")).upper()
        if feature in {"ON_OFF", "DIM", "WHITE"}:
            features.add(feature)
        if feature == "WHITE":
            configuration = row.get("configuration") or {}
            if isinstance(configuration, dict):
                low, high = configuration.get("min_cct"), configuration.get("max_cct")
                if isinstance(low, int) and isinstance(high, int) and 1500 <= low < high <= 7000:
                    device["_cct_range"] = (low, high)
    if features:
        device["_state_features"] = sorted(features)


def parse_state(rows):
    """Read documented humanized values; do not guess missing state."""
    result = {"on": None, "brightness": None, "kelvin": None}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).lower()
        human = str(row.get("humanized", "")).strip().lower()
        if name == "on_off" or (name.isdecimal() and human in {"on", "off"}):
            if human in {"on", "off", "1", "0"}:
                result["on"] = human in {"on", "1"}
        elif name == "dim":
            try:
                value = float(human.rstrip("%"))
                value = round(value * 255 / 100) if human.endswith("%") else round(value)
                result["brightness"] = max(0, min(255, value))
            except (ValueError, OverflowError):
                pass
        elif name == "white":
            try:
                value = int(human)
                if 1500 <= value <= 7000:
                    result["kelvin"] = value
            except ValueError:
                pass
    if result["on"] is None and result["brightness"] is not None:
        result["on"] = result["brightness"] > 0
    return result
