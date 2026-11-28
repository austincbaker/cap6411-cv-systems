#!/usr/bin/env python3
"""Read or set the built-in display's brightness and auto-brightness (macOS, no root).

    uv run python scripts/macos_display.py get                 # {"brightness": 0.68, ...}
    uv run python scripts/macos_display.py set-brightness 0.5
    uv run python scripts/macos_display.py auto-brightness off|on

Used by ``scripts/run_energy_suite_detached.sh`` to hold the display at a fixed level during an
energy suite. Brightness uses the private DisplayServices framework (the same one
``energy.macos.display_brightness`` reads); auto-brightness uses CoreDisplay's
``CoreDisplay_Display_SetAutoBrightnessIsEnabled``. macOS offers no unprivileged way to read the
auto-brightness setting back, so ``get`` reports it as unknown. True Tone is not touched.
Prints one JSON object; exits 1 when the call is unavailable.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import sys

DISPLAY_SERVICES = "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
CORE_DISPLAY = "/System/Library/Frameworks/CoreDisplay.framework/CoreDisplay"


def main_display() -> int:
    graphics = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
    graphics.CGMainDisplayID.restype = ctypes.c_uint32
    return graphics.CGMainDisplayID()


def get_brightness() -> float:
    services = ctypes.CDLL(DISPLAY_SERVICES)
    services.DisplayServicesGetBrightness.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_float),
    ]
    value = ctypes.c_float()
    status = services.DisplayServicesGetBrightness(main_display(), ctypes.byref(value))
    if status != 0:
        raise OSError(f"DisplayServicesGetBrightness returned {status}")
    return round(value.value, 4)


def set_brightness(level: float) -> None:
    if not 0.0 <= level <= 1.0:
        raise ValueError("brightness must be between 0 and 1")
    services = ctypes.CDLL(DISPLAY_SERVICES)
    services.DisplayServicesSetBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
    status = services.DisplayServicesSetBrightness(main_display(), ctypes.c_float(level))
    if status != 0:
        raise OSError(f"DisplayServicesSetBrightness returned {status}")


def set_auto_brightness(enabled: bool) -> None:
    display = ctypes.CDLL(CORE_DISPLAY)
    function = display.CoreDisplay_Display_SetAutoBrightnessIsEnabled
    function.argtypes = [ctypes.c_uint32, ctypes.c_bool]
    function.restype = None
    function(main_display(), enabled)


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["get"]:
            out = {"brightness": get_brightness(), "auto_brightness": "unknown (not readable)"}
        elif argv[:1] == ["set-brightness"] and len(argv) == 2:
            set_brightness(float(argv[1]))
            out = {"brightness": get_brightness()}
        elif argv[:1] == ["auto-brightness"] and argv[1:] in (["on"], ["off"]):
            set_auto_brightness(argv[1] == "on")
            out = {"auto_brightness_set": argv[1]}
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (OSError, AttributeError, ValueError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
