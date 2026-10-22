"""Exercise actual light command methods without installing Home Assistant."""
import ast
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "custom_components/halo_home_bridge/light.py"
light = next(n for n in ast.parse(source.read_text(encoding="utf-8-sig")).body
             if isinstance(n, ast.ClassDef) and n.name == "HaloLight")
methods = [n for n in light.body if isinstance(n, ast.AsyncFunctionDef)
           and n.name in {"async_turn_on", "async_turn_off"}]
namespace = {"ATTR_BRIGHTNESS": "brightness", "ATTR_COLOR_TEMP_KELVIN": "color_temp_kelvin"}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


class Lamp:
    async_turn_on = namespace["async_turn_on"]
    async_turn_off = namespace["async_turn_off"]
    min_color_temp_kelvin = 2700
    max_color_temp_kelvin = 5000
    brightness = 255

    def __init__(self, on, features=("ON_OFF", "DIM", "WHITE")):
        self.is_on = on
        self._features = set(features)
        self.commands = []

    async def _send(self, commands):
        self.commands.extend(commands)


def run(coroutine):
    # These methods await only immediate stubs; no event loop/network is needed.
    try:
        coroutine.send(None)
    except StopIteration:
        return
    raise AssertionError("Unexpected external await")


class LightCommandTests(unittest.TestCase):
    def test_dimming_on_lamp_has_no_trailing_on(self):
        lamp = Lamp(True)
        run(lamp.async_turn_on(brightness=51))
        self.assertEqual(lamp.commands, [("dim", "20%")])

    def test_off_or_unknown_lamp_turns_on_before_explicit_settings(self):
        for on in (False, None):
            lamp = Lamp(on)
            run(lamp.async_turn_on(brightness=51, color_temp_kelvin=4000))
            self.assertEqual(lamp.commands, [("on_off", "on"), ("white", "4000"), ("dim", "20%")])

    def test_zero_brightness_remains_off(self):
        lamp = Lamp(True)
        run(lamp.async_turn_on(brightness=0))
        self.assertEqual(lamp.commands, [("on_off", "off")])

    def test_plain_turn_on_and_dimmable_fallback(self):
        lamp = Lamp(False)
        run(lamp.async_turn_on())
        self.assertEqual(lamp.commands, [("on_off", "on")])
        lamp = Lamp(False, ("DIM",))
        run(lamp.async_turn_on(brightness=51))
        self.assertEqual(lamp.commands, [("dim", "20%")])
