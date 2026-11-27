"""Stand-in for ``powermetrics -f plist``: NUL-separated plist samples on stdout until killed.

    python tests/fakes/fake_powermetrics.py [interval_s] [cpu_mw] [gpu_mw]

Each sample reports the given constant powers over ``interval_s``, in the layout macOS uses
(``processor.cpu_power`` etc. in mW, ``elapsed_ns``). Used by tests and by stubbed suite runs
on machines without sudo; its numbers are synthetic.
"""

from __future__ import annotations

import plistlib
import sys
import time


def sample(interval_s: float, cpu_mw: float, gpu_mw: float) -> bytes:
    return plistlib.dumps(
        {
            "elapsed_ns": int(interval_s * 1e9),
            "thermal_pressure": "Nominal",
            "processor": {
                "cpu_power": cpu_mw,
                "gpu_power": gpu_mw,
                "ane_power": 0.0,
                "combined_power": cpu_mw + gpu_mw,
            },
        }
    )


def main() -> int:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
    cpu = float(sys.argv[2]) if len(sys.argv) > 2 else 2000.0
    gpu = float(sys.argv[3]) if len(sys.argv) > 3 else 500.0
    try:
        while True:
            time.sleep(interval)
            sys.stdout.buffer.write(sample(interval, cpu, gpu) + b"\x00")
            sys.stdout.buffer.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    sys.exit(main())
