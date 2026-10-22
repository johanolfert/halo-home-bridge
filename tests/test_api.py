"""Protocol tests without requiring Home Assistant or real credentials."""
import asyncio
import importlib
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
package = types.ModuleType("halo_under_test")
package.__path__ = [str(ROOT / "custom_components" / "halo_home_bridge")]
sys.modules[package.__name__] = package
api = importlib.import_module("halo_under_test.api")
presets = importlib.import_module("halo_under_test.presets")


class PresetTests(unittest.TestCase):
    def test_range_filters_unreachable_temperatures(self):
        result = presets.supported_presets(3000, 4000)
        self.assertEqual(set(result.values()), {3000, 3500, 4000})

    def test_custom_is_not_misreported_as_nearest_preset(self):
        self.assertEqual(presets.current_preset(3214, presets.CCT_PRESETS), "Custom")
        self.assertEqual(presets.current_preset(2700, presets.CCT_PRESETS), "Warm white (2700 K)")
        self.assertIsNone(presets.current_preset(None, presets.CCT_PRESETS))

    def test_settings_reject_invalid_values(self):
        for value in [float('nan'), float('inf'), 2699, 5001]:
            with self.assertRaises(ValueError):
                presets.validate_setting(value, 2700, 5000)




class Response:
    def __init__(self, status, payload):
        self.status, self.payload = status, payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return Response(*next(self.responses))


class StateTests(unittest.TestCase):
    def test_documented_state(self):
        self.assertEqual(api.parse_state([
            {"name": 76405, "humanized": "on"},
            {"name": "dim", "humanized": "50%"},
            {"name": "white", "humanized": "4438"},
        ]), {"on": True, "brightness": 128, "kelvin": 4438})

    def test_missing_and_invalid_values(self):
        self.assertEqual(api.parse_state([{ "name": "white", "humanized": "bad"},
            {"name": "dim", "humanized": "nan%"}]),
            {"on": None, "brightness": None, "kelvin": None})

    def test_off_takes_precedence_over_remembered_brightness(self):
        state = api.parse_state([{"name": "on_off", "humanized": "off"},
                                 {"name": "dim", "humanized": "100%"}])
        self.assertFalse(state["on"])

    def test_zero_dim_fallback(self):
        self.assertFalse(api.parse_state([{"name": "dim", "humanized": "0%"}])["on"])

    def test_filters_controllers_and_bridge(self):
        self.assertFalse(api.is_lamp({"pid": "bridge", "product": {"features": ["CLOCK"]}}))
        self.assertFalse(api.is_lamp({"pid": "group", "type": "group", "product": {"features": ["DIM"]}}))
        self.assertTrue(api.is_lamp({"pid": "lamp", "product": {"features": ["DIM", "WHITE"]}}))

    def test_actual_halo_product_without_features(self):
        device = {"pid": "lamp", "type": "device", "location_id": 123456,
                  "product": {"id": 137, "name": "Surface Downlight (BLD)", "category": "LIGHT"}}
        self.assertTrue(api.is_lamp(device))
        self.assertEqual(api.lamp_features(device), set())
        api.enrich_device(device, [
            {"name": "dim", "write": True}, {"name": "on_off", "write": True},
            {"name": "white", "write": True, "configuration": {"min_cct": 2700, "max_cct": 5000}},
            {"name": "clock", "write": False},
        ])
        self.assertEqual(api.lamp_features(device), {"ON_OFF", "DIM", "WHITE"})
        self.assertEqual(device["_cct_range"], (2700, 5000))

    def test_category_does_not_include_controller(self):
        self.assertFalse(api.is_lamp({"pid": "controller", "type": "controller",
                                     "product": {"category": "LIGHT"}}))

    def test_read_only_state_is_not_control_capability(self):
        device = {}
        api.enrich_device(device, [{"name": "white", "write": False}])
        self.assertEqual(api.lamp_features(device), set())

    def test_clock_snapshot_does_not_enable_clock_writes(self):
        device = {}
        api.enrich_device(device, [{"name": "clock", "write": False,
            "humanized": "0/0/0 0:0:0", "updated_at": "2026-08-12T04:00:09+00:00"}])
        self.assertFalse(device["_clock_info"]["writable"])
        self.assertEqual(device["_clock_info"]["reported_clock"], "0/0/0 0:0:0")
        self.assertNotIn("CLOCK", api.lamp_features(device))


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_commands_use_group_endpoint(self):
        session = Session([(200, {"state": {}})])
        client = api.HaloApi(session, {"auth_token": "a"})
        await client.set_feature("group", "white", "3000", "groups")
        self.assertTrue(session.calls[0][1].endswith("groups/group/state"))
        self.assertEqual(session.calls[0][2]["json"]["state"], {"feature": "white", "value": "3000"})

    async def test_scene_activation_and_feature_validation(self):
        session = Session([(200, {"state": {}})])
        client = api.HaloApi(session, {"auth_token": "a"})
        await client.set_feature("scene", "action", "on", "scenes")
        self.assertTrue(session.calls[0][1].endswith("scenes/scene/state"))
        with self.assertRaises(ValueError):
            await client.set_feature("scene", "dim", "50%", "scenes")

    async def test_location_mapping_does_not_choose_wrong_mesh(self):
        session = Session([(200, {"locations": [{"pid": "other"}, {"pid": "home"}]}),
                           (200, {"location": {"id": 8}}), (200, {"location": {"id": 9}})])
        client = api.HaloApi(session, {"auth_token": "a"})
        self.assertEqual(await client.location_pid("9"), "home")
        self.assertEqual(session.calls[0][2]["headers"]["Accept"], "application/vnd.avi-on.v3+json")

    async def test_catalog_requires_list(self):
        client = api.HaloApi(Session([(200, {"schedules": {}})]), {"auth_token": "a"})
        with self.assertRaises(api.ApiError):
            await client.catalog("home", "schedules")

    async def test_bridge_status_omits_network_secrets(self):
        client = api.HaloApi(Session([(200, {"rabs": [{"pid": "bridge", "remote_status": "offline", "ssid": "private", "device_key": "secret"}]})]), {"auth_token": "a"})
        result = await client.bridges("loc")
        self.assertEqual(result[0]["remote_status"], "offline")
        self.assertNotIn("ssid", result[0])
        self.assertNotIn("device_key", result[0])

    async def test_login_does_not_retain_password(self):
        session = Session([(201, {"credentials": {"auth_token": "a", "refresh_token": "r", "password": "secret"}})])
        client = api.HaloApi(session)
        await client.login("test@example.com", "secret")
        self.assertNotIn("password", client.credentials)
        self.assertEqual(session.calls[0][2]["headers"]["Accept"], "application/vnd.avi-on.v2+json")
        self.assertFalse(session.calls[0][2]["allow_redirects"])

    async def test_refresh_and_persist_new_tokens(self):
        session = Session([(401, {}), (200, {"credentials": {"auth_token": "new", "refresh_token": "next"}}), (200, {"devices": []})])
        saved = []
        client = api.HaloApi(session, {"auth_token": "old", "refresh_token": "r"}, saved.append)
        self.assertEqual(await client.devices(), [])
        self.assertEqual(session.calls[1][2]["headers"]["Authorization"], "RefreshToken r")
        self.assertEqual(session.calls[2][2]["headers"]["Authorization"], "Token new")
        self.assertEqual(saved[0]["refresh_token"], "next")

    async def test_expired_refresh_requires_reauth(self):
        client = api.HaloApi(Session([(401, {}), (401, {})]), {"auth_token": "old", "refresh_token": "r"})
        with self.assertRaises(api.AuthenticationError):
            await client.devices()

    async def test_retry_is_bounded(self):
        session = Session([(401, {}), (200, {"credentials": {"auth_token": "new"}}), (401, {})])
        client = api.HaloApi(session, {"auth_token": "old", "refresh_token": "r"})
        with self.assertRaises(api.AuthenticationError):
            await client.devices()
        self.assertEqual(len(session.calls), 3)

    async def test_command_encoding(self):
        session = Session([(200, {"state": {}})])
        client = api.HaloApi(session, {"auth_token": "a"})
        await client.set_feature("lamp/a?", "dim", "50%")
        method, url, args = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("devices/lamp%2Fa%3F/state"))
        self.assertEqual(args["json"], {"state": {"feature": "dim", "value": "50%"}})

    async def test_error_does_not_expose_response(self):
        client = api.HaloApi(Session([(403, {"secret": "private"})]), {"auth_token": "a"})
        with self.assertRaisesRegex(api.ApiError, "HTTP 403") as error:
            await client.devices()
        self.assertNotIn("private", str(error.exception))

    async def test_invalid_catalog_and_state_rejected(self):
        client = api.HaloApi(Session([(200, {"devices": {}}), (200, {"state": {}})]), {"auth_token": "a"})
        with self.assertRaises(api.ApiError):
            await client.devices()
        with self.assertRaises(api.ApiError):
            await client.state("lamp")


if __name__ == "__main__":
    unittest.main()


