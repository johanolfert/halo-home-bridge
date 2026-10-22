"""Pure control helpers for CCT presets and sliders."""
import math

CCT_PRESETS = {
    "Warm white (2700 K)": 2700,
    "Soft white (3000 K)": 3000,
    "Neutral white (3500 K)": 3500,
    "Cool white (4000 K)": 4000,
    "Daylight (5000 K)": 5000,
}


def supported_presets(low, high):
    return {name: value for name, value in CCT_PRESETS.items() if low <= value <= high}


def current_preset(kelvin, presets):
    if kelvin is None:
        return None
    return next((name for name, value in presets.items() if abs(kelvin - value) <= 1), "Custom")


def validate_setting(value, low, high):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Value is outside the supported range")
    return round(value)


