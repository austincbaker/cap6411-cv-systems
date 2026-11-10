"""Fixed-interval baseline application (item 1d).

    python -m app.main --source replay --video clip.mp4 --interval-s 2 --no-display
    python -m app.main --source webcam --device 0 --interval-s 2 --duration-s 60

Every ``--interval-s`` seconds (ticks at ``t0 + k * interval`` on the monotonic
clock, no drift) the newest source frame is sent to the VLM. With
``--policy gated`` (item 2a) a tick is sent only when ``gates.ChangeGate``
triggers; gate skips go to ``drops.jsonl`` with origin ``gate``. At most one
request is in flight. A tick that fires while a request is still running is
skipped and logged as ``tick_skipped_busy`` with the frame ID it would have
sent; nothing is queued. Source acquisition runs on its own thread, so slow
inference never slows or pauses capture/replay.

Run directory (``--run-dir``, default ``runs/<UTC time>_<source>/``):

- ``requests.jsonl``  one line per request (frame identity, source time,
  host request start / response-available times, status, text or error type)
- ``drops.jsonl``     skipped ticks and frames the source dropped, with IDs and reasons
- ``power.csv``       power/energy samples, one row per sensor reading
- ``manifest.json``   config, source metadata, end reasons, counts, power state, platform

All ``host_*`` times are ``time.monotonic()`` seconds in this process;
``source_time_s`` is media-relative (None for webcam). The file formats are the
item 2d contract in ``docs/data-contracts.md``, checked by ``contracts``.

Exit codes: 0 completed (EOF, --duration-s, or 'q' in the window), 2 bad
config / source failed to open / source ended in error, 130 interrupted,
1 unexpected application error.

Inference uses ``vlm.client.VLMClient`` against an already running
llama-server configured by ``--profile`` (default ``configs/inference.json``;
start it with ``scripts/llama_runtime.py serve``). The app checks the server
before creating a run directory. After a request whose server-side state is
unknown (a read timeout), no new request is sent until the server reports no
busy slot; ticks in between are logged as ``tick_skipped_server_unknown``.

Telemetry (``--telemetry on``) logs two sources, each row labeled with its
``source``: Linux sysfs readings from ``energy.monitor.EnergyMonitor`` and the
Windows battery report from ``energy.windows.WindowsBatteryReader`` (the
qualified whole-laptop source on the WSL2 platform; unavailable elsewhere).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import platform
import queue
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import cv2
import httpx
import numpy as np

from app.state import ObservationState, render_overlay
from capture import EndReason, Frame, ReplaySource, SourceBase, SourceOpenError, WebcamSource
from contracts import CONTRACT_VERSION, RUN_FILES, SCHEMAS, csv_row
from energy.monitor import EnergyMonitor
from energy.windows import WindowsBatteryReader
from gates import ChangeGate, GateConfig
from vlm.client import VLMClient, VLMConfig

SCHEMA_VERSION = CONTRACT_VERSION
POLICIES = ("fixed_interval", "gated")
WINDOW_NAME = "cap6411 baseline"
SERVER_PROPERTY_KEYS = ("build_info", "model_path", "model_alias", "total_slots", "modalities")


# ============================================================================ CLI


class ConfigError(Exception):
    pass


def positive_float(text: str) -> float:
    value = float(text)
    if not value > 0 or value == float("inf"):
        raise argparse.ArgumentTypeError(f"must be a positive number, got {text}")
    return value


def nonnegative_float(text: str) -> float:
    value = float(text)
    if not value >= 0 or value == float("inf"):
        raise argparse.ArgumentTypeError(f"must be >= 0, got {text}")
    return value


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="Fixed-interval VLM baseline over a webcam or real-time video replay.",
        allow_abbrev=False,
    )
    src = parser.add_argument_group("source")
    src.add_argument("--source", choices=("webcam", "replay"), required=True)
    src.add_argument("--video", help="video file for --source replay")
    src.add_argument(
        "--device", default="0", help="camera index or device path for --source webcam (default 0)"
    )
    src.add_argument(
        "--width", type=positive_int, help="requested camera width (observed value is recorded)"
    )
    src.add_argument(
        "--height", type=positive_int, help="requested camera height (observed value is recorded)"
    )
    src.add_argument(
        "--camera-fps",
        type=positive_float,
        help="requested camera fps (observed value is recorded)",
    )

    sched = parser.add_argument_group("schedule")
    sched.add_argument(
        "--interval-s",
        type=positive_float,
        default=2.0,
        help="seconds between VLM invocations (default 2)",
    )
    sched.add_argument(
        "--policy",
        choices=POLICIES,
        default="fixed_interval",
        help="fixed_interval sends every tick; gated sends a tick only when the change gate triggers",
    )
    sched.add_argument(
        "--duration-s",
        type=positive_float,
        help="stop after this many seconds (default: until EOF / q / Ctrl-C)",
    )

    gate = parser.add_argument_group("gate (--policy gated)")
    gate.add_argument(
        "--gate-threshold",
        type=positive_float,
        default=GateConfig.threshold,
        help=f"changed fraction of the most-changed cell that triggers (default {GateConfig.threshold})",
    )
    gate.add_argument(
        "--gate-pixel-delta",
        type=int,
        default=GateConfig.pixel_delta,
        help=f"brightness change 0-255 that marks a pixel changed (default {GateConfig.pixel_delta})",
    )
    gate.add_argument(
        "--gate-grid",
        type=positive_int,
        default=GateConfig.grid,
        help=f"cells per side for the regional score; 1 = global (default {GateConfig.grid})",
    )
    gate.add_argument(
        "--gate-min-interval-s",
        type=nonnegative_float,
        default=GateConfig.min_interval_s,
        help="minimum seconds between gate triggers (default 0)",
    )
    gate.add_argument(
        "--gate-refresh-s",
        type=positive_float,
        help="force a call after this many seconds without one (default: never)",
    )

    req = parser.add_argument_group("request")
    req.add_argument(
        "--profile",
        default="configs/inference.json",
        help="inference profile (default configs/inference.json)",
    )
    req.add_argument("--prompt", default="Describe the visible objects in one short sentence.")
    req.add_argument(
        "--max-tokens",
        type=positive_int,
        help="output bound per request (default and maximum: the profile's)",
    )
    req.add_argument(
        "--request-timeout-s",
        type=positive_float,
        help="read timeout per request (default: the profile's)",
    )
    req.add_argument("--jpeg-quality", type=int, choices=range(1, 101), metavar="1-100", default=85)
    req.add_argument(
        "--server-idle-timeout-s",
        type=positive_float,
        default=60.0,
        help="after an uncertain timeout, end the run if the server is not idle within this time (default 60)",
    )

    tel = parser.add_argument_group("telemetry")
    tel.add_argument("--telemetry", choices=("on", "off"), default="on")
    tel.add_argument(
        "--telemetry-interval-s",
        type=positive_float,
        default=1.0,
        help="sysfs sample interval (default 1)",
    )
    tel.add_argument(
        "--battery-interval-s",
        type=positive_float,
        default=10.0,
        help="Windows battery report interval (default 10; the report itself updates every ~30-40 s)",
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "--run-dir",
        help="output directory (default runs/<UTC time>_<source>/); must not already contain files",
    )
    out.add_argument("--no-display", action="store_true", help="headless: no OpenCV window")
    out.add_argument(
        "--shutdown-timeout-s",
        type=nonnegative_float,
        default=5.0,
        help="max wait for threads/in-flight request when interrupted",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source == "replay" and not args.video:
        parser.error("--source replay requires --video PATH")
    if args.source == "webcam" and args.video:
        parser.error("--video is only valid with --source replay")
    try:
        args.gate_config = gate_config(args)
    except ValueError as exc:
        parser.error(f"gate: {exc}")
    return args


def gate_config(config: argparse.Namespace) -> GateConfig:
    return GateConfig(
        threshold=config.gate_threshold,
        pixel_delta=config.gate_pixel_delta,
        min_interval_s=config.gate_min_interval_s,
        refresh_s=config.gate_refresh_s,
        grid=config.gate_grid,
    )


# ============================================================================ builders


def build_source(config: argparse.Namespace, on_drop) -> SourceBase:
    if config.source == "replay":
        return ReplaySource(config.video, on_drop=on_drop)
    return WebcamSource(
        config.device,
        width=config.width,
        height=config.height,
        fps=config.camera_fps,
        on_drop=on_drop,
    )


def load_vlm_config(config: argparse.Namespace) -> VLMConfig:
    """VLMConfig from the inference profile, with the CLI's timeout override."""
    try:
        profile = json.loads(Path(config.profile).read_text())
        vlm = VLMConfig(
            base_url=f"http://{profile['host']}:{profile['port']}",
            model=profile["model_alias"],
            max_output_tokens=profile["max_output_tokens"],
            connect_timeout_s=profile["connect_timeout_s"],
            read_timeout_s=config.request_timeout_s or profile["read_timeout_s"],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConfigError(
            f"cannot load inference profile {config.profile}: {type(exc).__name__}: {exc}"
        )
    if config.max_tokens is not None and config.max_tokens > vlm.max_output_tokens:
        raise ConfigError(
            f"--max-tokens {config.max_tokens} exceeds the profile bound {vlm.max_output_tokens}"
        )
    return vlm


def check_server(client: VLMClient) -> dict:
    """The running server's identity; ConfigError if it does not answer."""
    try:
        props = client.server_properties()
    except (httpx.HTTPError, ValueError) as exc:
        raise ConfigError(
            f"no ready llama-server at {client.config.base_url} ({type(exc).__name__}); "
            "start it with `uv run python scripts/llama_runtime.py serve`"
        )
    return {key: props.get(key) for key in SERVER_PROPERTY_KEYS}


def server_is_idle(base_url: str) -> bool:
    """True only when llama-server's /slots reports no slot processing."""
    try:
        response = httpx.get(base_url.rstrip("/") + "/slots", timeout=2.0, trust_env=False)
        slots = response.json() if response.is_success else None
    except (httpx.HTTPError, ValueError):
        return False
    return (
        isinstance(slots, list)
        and bool(slots)
        and not any(isinstance(slot, dict) and slot.get("is_processing") for slot in slots)
    )


# ============================================================================ plumbing


class JsonlWriter:
    """Thread-safe append-only JSONL file, flushed per line so interrupted runs keep their records."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._file = open(path, "a", encoding="utf-8")
        self.lines = 0

    def write(self, record: dict) -> None:
        line = json.dumps(record, default=str)
        with self._lock:
            if self._file.closed:
                return
            self._file.write(line + "\n")
            self._file.flush()
            self.lines += 1

    def close(self) -> None:
        with self._lock:
            self._file.close()


class CsvWriter:
    """Thread-safe append-only CSV in a contract layout (header first, flushed per row)."""

    def __init__(self, path: Path, kind: str) -> None:
        self.kind = kind
        self._lock = threading.Lock()
        self._file = open(path, "w", encoding="utf-8", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow([f.name for f in SCHEMAS[kind]])
        self._file.flush()
        self.lines = 0

    def write(self, record: dict) -> None:
        with self._lock:
            if self._file.closed:
                return
            self._writer.writerow(csv_row(self.kind, record))
            self._file.flush()
            self.lines += 1

    def close(self) -> None:
        with self._lock:
            self._file.close()


class LatestFrameSlot:
    """Holds only the newest frame from the capture thread; older frames are overwritten, never queued."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[Frame] = None
        self.first_frame = threading.Event()
        self.closed = threading.Event()
        self.error: Optional[BaseException] = None

    def put(self, frame: Frame) -> None:
        with self._lock:
            self._frame = frame
        self.first_frame.set()

    def latest(self) -> Optional[Frame]:
        with self._lock:
            return self._frame


def encode_jpeg(image: np.ndarray, quality: int) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buffer.tobytes()


def default_run_dir(source: str) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path("runs") / f"{stamp}_{source}"
    path, n = base, 1
    while path.exists():
        n += 1
        path = base.with_name(f"{base.name}_{n}")
    return path


def prepare_run_dir(config: argparse.Namespace) -> Path:
    path = Path(config.run_dir) if config.run_dir else default_run_dir(config.source)
    if path.exists() and any(path.iterdir()):
        raise ConfigError(f"run directory {path} already contains files; refusing to overwrite")
    path.mkdir(parents=True, exist_ok=True)
    return path


# ============================================================================ run


@dataclass
class RunResult:
    exit_code: int
    run_dir: Path
    manifest: dict = field(default_factory=dict)


class BaselineRun:
    def __init__(
        self,
        config: argparse.Namespace,
        *,
        source_factory: Optional[Callable[..., SourceBase]] = None,
        client: Optional[VLMClient] = None,
        energy_monitor: Optional[EnergyMonitor] = None,
        battery_reader: Optional[WindowsBatteryReader] = None,
        server_idle: Optional[Callable[[], bool]] = None,
        argv: Optional[Sequence[str]] = None,
    ) -> None:
        self.config = config
        self.argv = list(argv) if argv is not None else None
        self.run_id = uuid.uuid4().hex
        # Check the backends before touching the filesystem so config errors leave nothing behind.
        self.client = client if client is not None else VLMClient(load_vlm_config(config))
        self.max_tokens = config.max_tokens or self.client.config.max_output_tokens
        if self.max_tokens > self.client.config.max_output_tokens:
            raise ConfigError(
                f"--max-tokens {self.max_tokens} exceeds the client bound {self.client.config.max_output_tokens}"
            )
        try:
            self.server_properties = check_server(self.client)
        except ConfigError:
            self.client.close()
            raise
        self.server_idle = server_idle or (lambda: server_is_idle(self.client.config.base_url))
        if config.telemetry == "on":
            self.energy_monitor = energy_monitor or EnergyMonitor(run_id=self.run_id)
            self.battery_reader = battery_reader or WindowsBatteryReader()
        else:
            self.energy_monitor = self.battery_reader = None
        self.run_dir = prepare_run_dir(config)
        self.requests_log = JsonlWriter(self.run_dir / RUN_FILES["request"])
        self.drops_log = JsonlWriter(self.run_dir / RUN_FILES["schedule"])
        self.power_log = CsvWriter(self.run_dir / RUN_FILES["power"], "power")
        # source_factory(on_drop) lets tests inject a source wired to this run's drop log.
        factory = source_factory or (lambda on_drop: build_source(config, on_drop))
        self.source = factory(self._on_source_drop)
        self.state = ObservationState()
        self.gate = ChangeGate(config.gate_config) if config.policy == "gated" else None
        self.slot = LatestFrameSlot()
        self.jobs: "queue.Queue[Optional[tuple]]" = queue.Queue(maxsize=1)
        self.results: "queue.Queue[dict]" = queue.Queue()
        self.telemetry_stop = threading.Event()
        self.threads: list[threading.Thread] = []
        self.capture_thread: Optional[threading.Thread] = None
        self.in_flight: Optional[dict] = None
        self.server_unknown_since: Optional[float] = (
            None  # set after a request with server_state_unknown
        )
        self.client_closed = False
        self.display = not config.no_display
        self.display_error: Optional[str] = None
        self.run_end_reason: Optional[str] = None
        self.error_detail: Optional[str] = None
        self.manifest: dict = {}
        # First and last valid Windows battery report (AC/battery state for the manifest).
        self.power_state: dict[str, Optional[dict]] = {"at_start": None, "at_end": None}
        self.times: dict[str, Optional[float]] = {
            "host_run_start_s": None,
            "host_tick_origin_s": None,
            "host_run_end_s": None,
        }

    # -- entry -------------------------------------------------------------
    def run(self) -> RunResult:
        self.times["host_run_start_s"] = time.monotonic()
        self.started_wall_utc = dt.datetime.now(dt.timezone.utc).isoformat()
        exit_code = 1
        interrupted = False
        try:
            try:
                self.source.open()
            except SourceOpenError as exc:
                self.run_end_reason = "source_open_failed"
                self.error_detail = str(exc)
                print(f"error: {exc}", file=sys.stderr)
                return self._finalize(2, interrupted=False)
            self._start_threads()
            self._main_loop()
            exit_code = self._exit_code_for_source_end()
        except KeyboardInterrupt:
            interrupted = True
            self.run_end_reason = "interrupted"
            exit_code = 130
        except Exception as exc:  # unexpected: keep the run record, then report
            self.run_end_reason = "app_error"
            self.error_detail = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            exit_code = 1
        return self._finalize(exit_code, interrupted=interrupted)

    # -- threads -----------------------------------------------------------
    def _start_threads(self) -> None:
        self.capture_thread = self._spawn("capture", self._capture_loop)
        self._spawn("inference", self._inference_loop)
        if self.energy_monitor is not None:
            self._spawn(
                "telemetry-sysfs",
                lambda: self._telemetry_loop(self.config.telemetry_interval_s, self._sysfs_rows),
            )
        if self.battery_reader is not None:
            self._spawn(
                "telemetry-battery",
                lambda: self._telemetry_loop(self.config.battery_interval_s, self._battery_rows),
            )

    def _spawn(self, name: str, target: Callable[[], None]) -> threading.Thread:
        # daemon=True only as a last resort if a client ignores its timeout; shutdown always joins.
        thread = threading.Thread(target=target, name=f"baseline-{name}", daemon=True)
        self.threads.append(thread)
        thread.start()
        return thread

    def _capture_loop(self) -> None:
        try:
            with self.source:
                for frame in self.source:
                    self.slot.put(frame)
        except BaseException as exc:
            self.slot.error = exc
        finally:
            self.slot.closed.set()

    def _inference_loop(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            self.results.put(self._execute(*job))

    def _execute(
        self,
        frame: Frame,
        jpeg: bytes,
        encode_s: float,
        tick_index: int,
        host_tick_s: float,
        gate_fields: Optional[dict] = None,
    ) -> dict:
        app_fields = {
            **(gate_fields or {}),
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "tick_index": tick_index,
            "frame_id": frame.frame_id,
            "source_kind": frame.source_kind,
            "source_time_s": frame.source_time_s,
            "host_capture_s": frame.host_capture_s,
            "host_tick_s": host_tick_s,
            "encode_s": encode_s,
            "image_bytes": len(jpeg),
        }
        started = time.monotonic()
        try:
            result = self.client.infer(
                jpeg,
                frame_id=str(frame.frame_id),
                prompt=self.config.prompt,
                source_id=self.source.source_id,
                source_time_s=frame.source_time_s,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:  # local validation or a client bug: visible, never retried
            ended = time.monotonic()
            return {
                **app_fields,
                "status": "client_exception",
                "text": None,
                "error": f"{type(exc).__name__}: {exc}",
                "request_id": None,
                "request_started_s": started,
                "response_available_s": ended,
                "elapsed_s": ended - started,
                "server_state_unknown": False,
            }
        return {**result.to_dict(), **app_fields}

    def _telemetry_loop(self, interval: float, rows: Callable[[], list[dict]]) -> None:
        next_t = time.monotonic()
        while not self.telemetry_stop.is_set():
            try:
                batch = rows()
            except Exception as exc:  # a reader bug must not end the run silently
                batch = [
                    {
                        "source": "telemetry_error",
                        "sensor_id": getattr(rows, "__name__", "telemetry"),
                        "domain": "unknown",
                        "quantity": "unknown",
                        "host_time_s": time.monotonic(),
                        "valid": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ]
            for row in batch:
                self.power_log.write(
                    {"schema_version": SCHEMA_VERSION, "run_id": self.run_id, **row}
                )
            next_t += interval
            self.telemetry_stop.wait(max(0.0, next_t - time.monotonic()))

    def _sysfs_rows(self) -> list[dict]:
        # Reading.elapsed_s counts from the monitor's origin; put it on the shared host clock.
        origin = self.energy_monitor.origin_s
        return [
            {
                "source": "sysfs",
                "sensor_id": r.sensor_id,
                "domain": r.domain,
                "quantity": r.quantity,
                "host_read_start_s": None,
                "host_time_s": origin + r.elapsed_s,
                "raw_value": r.raw_value,
                "raw_unit": r.raw_unit,
                "value": r.value if r.valid else None,
                "unit": r.unit,
                "valid": r.valid,
                "error": r.error,
                "ac_online": r.ac_online,
                "battery_status": r.battery_status,
                "quality_flags": r.quality_flags or None,
            }
            for r in self.energy_monitor.sample()
        ]

    def _battery_rows(self) -> list[dict]:
        """One Windows battery report as two rows: stored energy and discharge power."""
        reading = self.battery_reader.read()
        if reading.valid:
            snapshot = {
                "host_time_s": reading.available_s,
                "ac_online": reading.ac_online,
                "battery_status": reading.battery_status,
                "power_supply_status": reading.power_supply_status,
                "remaining_mwh": reading.remaining_mwh,
                "full_mwh": reading.full_mwh,
            }
            if self.power_state["at_start"] is None:
                self.power_state["at_start"] = snapshot
            self.power_state["at_end"] = snapshot
        common = {
            "source": "windows_battery",
            "domain": "whole_laptop_battery",
            "host_read_start_s": reading.started_s,
            "host_time_s": reading.available_s,
            "ac_online": reading.ac_online,
            "battery_status": reading.battery_status,
            "quality_flags": None if reading.on_battery else "not_verified_discharging",
        }
        rate_ok = reading.valid and reading.charge_rate_mw is not None
        return [
            {
                **common,
                "sensor_id": "windows:aggregate:remaining_capacity",
                "quantity": "stored_energy",
                "raw_value": reading.remaining_mwh,
                "raw_unit": "mWh",
                "value": reading.energy_j if reading.valid else None,
                "unit": "J",
                "valid": reading.valid,
                "error": reading.error,
            },
            {
                **common,
                "sensor_id": "windows:aggregate:charge_rate",
                "quantity": "discharge_power",
                "raw_value": reading.charge_rate_mw,
                "raw_unit": "mW",
                "value": reading.discharge_power_w if rate_ok else None,
                "unit": "W",
                "valid": rate_ok,
                "error": None if rate_ok else (reading.error or "charge_rate_unavailable"),
            },
        ]

    # -- logging -----------------------------------------------------------
    def _on_source_drop(
        self, frame_id: int, reason: str, host_time_s: float, detail: str = ""
    ) -> None:
        # Called on the capture thread.
        self.drops_log.write(
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "origin": "source",
                "reason": reason,
                "frame_id": frame_id,
                "host_time_s": host_time_s,
                "detail": detail,
            }
        )

    def _log_tick_drop(
        self,
        reason: str,
        tick_index: int,
        host_tick_s: float,
        frame: Frame,
        origin: str = "app",
        **extra: Any,
    ) -> None:
        self.state.bump(reason)
        self.drops_log.write(
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "origin": origin,
                "reason": reason,
                "tick_index": tick_index,
                "host_tick_s": host_tick_s,
                "host_time_s": time.monotonic(),
                "frame_id": frame.frame_id,
                "source_time_s": frame.source_time_s,
                **extra,
            }
        )

    def _handle_result(self, record: dict) -> None:
        self.requests_log.write(record)
        self.state.record_result(
            status=record["status"],
            text=record["text"],
            error_type=record.get("error"),
            request_id=record["request_id"],
            frame_id=record["frame_id"],
            source_time_s=record["source_time_s"],
            host_capture_s=record["host_capture_s"],
            host_response_available_s=record["response_available_s"],
        )
        if record.get("server_state_unknown") and self.server_unknown_since is None:
            self.server_unknown_since = time.monotonic()
        self.in_flight = None

    def _drain_results(self, timeout: float = 0.0) -> None:
        try:
            record = self.results.get(timeout=timeout) if timeout > 0 else self.results.get_nowait()
        except queue.Empty:
            return
        self._handle_result(record)
        while True:
            try:
                self._handle_result(self.results.get_nowait())
            except queue.Empty:
                return

    # -- main loop ---------------------------------------------------------
    def _main_loop(self) -> None:
        interval = self.config.interval_s
        while not self.slot.first_frame.wait(0.05):
            if self.slot.closed.is_set():
                return
        tick_origin = time.monotonic()
        self.times["host_tick_origin_s"] = tick_origin
        end_at = tick_origin + self.config.duration_s if self.config.duration_s else None
        tick_index = 0
        next_tick = tick_origin
        last_draw = -1.0

        while True:
            self._drain_results()
            now = time.monotonic()
            if end_at is not None and now >= end_at and self.run_end_reason is None:
                self.run_end_reason = "duration_limit"
                self.source.stop()
            if self.run_end_reason == "duration_limit" and not self.slot.closed.is_set():
                self.slot.closed.wait(0.05)
                continue
            if self.slot.closed.is_set():
                return  # no dispatch after the source ends; shutdown collects any in-flight request

            if now >= next_tick:
                frame = self.slot.latest()
                if self.in_flight is not None:
                    self._log_tick_drop(
                        "tick_skipped_busy",
                        tick_index,
                        next_tick,
                        frame,
                        in_flight_frame_id=self.in_flight["frame_id"],
                    )
                elif self.server_unknown_since is not None and not self.server_idle():
                    self._log_tick_drop("tick_skipped_server_unknown", tick_index, next_tick, frame)
                    if now - self.server_unknown_since > self.config.server_idle_timeout_s:
                        self.run_end_reason = "server_not_idle"
                        self.error_detail = (
                            f"llama-server not idle {self.config.server_idle_timeout_s} s "
                            "after a request with unknown server state"
                        )
                        self.source.stop()
                elif (
                    decision := self._gate_decision(frame, now)
                ) is not None and not decision.trigger:
                    self.server_unknown_since = None
                    self._log_tick_drop(
                        decision.reason,
                        tick_index,
                        next_tick,
                        frame,
                        origin="gate",
                        **{k: v for k, v in decision.log_fields().items() if k != "gate_reason"},
                    )
                else:
                    self.server_unknown_since = None
                    gate_fields = None
                    if decision is not None:
                        self.gate.acknowledge(decision, now)
                        self.state.bump(decision.reason)
                        gate_fields = decision.log_fields()
                    encode_start = time.monotonic()
                    jpeg = encode_jpeg(frame.image, self.config.jpeg_quality)
                    encode_s = time.monotonic() - encode_start
                    self.in_flight = {
                        "request_id": None,
                        "tick_index": tick_index,
                        "frame_id": frame.frame_id,
                        "source_kind": frame.source_kind,
                        "source_time_s": frame.source_time_s,
                        "host_capture_s": frame.host_capture_s,
                        "host_tick_s": next_tick,
                        "request_started_s": time.monotonic(),
                    }
                    self.state.record_dispatch(frame.frame_id)
                    self.jobs.put_nowait(
                        (frame, jpeg, encode_s, tick_index, next_tick, gate_fields)
                    )
                # A late tick is still handled once, on the next pass; host_tick_s keeps its scheduled time.
                tick_index += 1
                next_tick = tick_origin + tick_index * interval

            if self.display and now - last_draw >= 1 / 30:
                last_draw = now
                self._draw()

            wait = max(0.0, min(next_tick - time.monotonic(), 0.02 if self.display else 0.05))
            self._drain_results(timeout=wait)

    def _gate_decision(self, frame: Frame, now: float):
        """The gate's verdict on this tick's frame, or None under fixed_interval."""
        return None if self.gate is None else self.gate.decide(frame.image, now)

    def _draw(self) -> None:
        frame = self.slot.latest()
        if frame is None:
            return
        try:
            cv2.imshow(
                WINDOW_NAME, render_overlay(frame.image, self.state.overlay_lines(time.monotonic()))
            )
            key = cv2.waitKey(1) & 0xFF
        except cv2.error as exc:
            self.display = False
            self.display_error = str(exc).strip()
            print(
                f"warning: display failed ({self.display_error}); continuing headless",
                file=sys.stderr,
            )
            return
        if key in (ord("q"), 27) and self.run_end_reason is None:
            self.run_end_reason = "user_quit"
            self.source.stop()

    # -- shutdown ----------------------------------------------------------
    def _exit_code_for_source_end(self) -> int:
        if self.slot.error is not None:
            self.run_end_reason = "capture_error"
            self.error_detail = f"{type(self.slot.error).__name__}: {self.slot.error}"
            return 1
        end = self.source.end
        if end is None:
            self.run_end_reason = "source_ended_without_reason"
            return 1
        if end.reason.is_error:
            self.run_end_reason = end.reason.value
            return 2
        if self.run_end_reason == "server_not_idle":
            return 2
        if self.run_end_reason is None:  # not already "user_quit" or "duration_limit"
            self.run_end_reason = end.reason.value
        return 0

    def _finalize(self, exit_code: int, *, interrupted: bool) -> RunResult:
        grace = self.config.shutdown_timeout_s
        if not self.source.end:
            self.source.stop(EndReason.INTERRUPTED if interrupted else EndReason.STOPPED)
        if interrupted:
            self._close_client()  # ask the client to abandon the in-flight request
        if self.capture_thread is not None:
            self.capture_thread.join(grace)
        if self.capture_thread is None or not self.capture_thread.is_alive():
            self.source.close()  # normally already closed by the capture thread's `with`

        if self.in_flight is not None:
            wait = grace if interrupted else self.client.config.read_timeout_s + grace
            deadline = time.monotonic() + wait
            while self.in_flight is not None and time.monotonic() < deadline:
                self._drain_results(timeout=min(0.05, max(0.0, deadline - time.monotonic())))
        if self.in_flight is not None:
            self.requests_log.write(
                {
                    "schema_version": SCHEMA_VERSION,
                    "run_id": self.run_id,
                    **self.in_flight,
                    "status": "abandoned_at_shutdown",
                    "response_available_s": None,
                    "text": None,
                    "error": "abandoned_at_shutdown",
                    "server_state_unknown": True,
                }
            )
            self.state.bump("status:abandoned_at_shutdown")
            self.in_flight = None
        try:
            self.jobs.put_nowait(None)
        except queue.Full:
            pass
        self.telemetry_stop.set()
        for thread in self.threads:
            thread.join(grace)
        self._close_client()
        if not self.config.no_display:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except cv2.error:
                pass

        self.times["host_run_end_s"] = time.monotonic()
        self.manifest = self._build_manifest(exit_code)
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2, default=str) + "\n"
        )
        for log in (self.requests_log, self.drops_log, self.power_log):
            log.close()
        return RunResult(exit_code=exit_code, run_dir=self.run_dir, manifest=self.manifest)

    def _close_client(self) -> None:
        if self.client_closed:
            return
        self.client_closed = True
        try:
            self.client.close()
        except Exception:
            pass

    def _build_manifest(self, exit_code: int) -> dict:
        info = self.source.info.as_dict()
        start = self.times["host_tick_origin_s"]
        end = self.times["host_run_end_s"]
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "policy": self.config.policy,
            "gate": None if self.gate is None else self.gate.config.as_dict(),
            "run_dir": str(self.run_dir),
            "argv": self.argv,
            "config": {k: v for k, v in vars(self.config).items() if k != "gate_config"},
            "started_wall_utc": self.started_wall_utc,
            "time_bases": {
                "host_*": "time.monotonic() seconds in this process",
                "source_time_s": "media-relative seconds (replay); null for webcam",
            },
            "times": {
                **self.times,
                "observed_duration_s": (end - start)
                if start is not None and end is not None
                else None,
            },
            "run_end_reason": self.run_end_reason,
            "exit_code": exit_code,
            "error_detail": self.error_detail,
            "files": {kind: name for kind, name in RUN_FILES.items() if kind != "manifest"},
            "power_state": self.power_state,
            "source": {"info": info, "end": self.source.end.as_dict() if self.source.end else None},
            "vlm": {
                "config": asdict(self.client.config),
                "max_tokens": self.max_tokens,
                "server_properties": self.server_properties,
            },
            "telemetry": (
                {"enabled": False}
                if self.energy_monitor is None
                else {
                    "enabled": True,
                    "sysfs_interval_s": self.config.telemetry_interval_s,
                    "sysfs_inventory": self.energy_monitor.inventory(),
                    "battery_interval_s": self.config.battery_interval_s,
                    "battery_source": "Windows.Devices.Power.BatteryReport",
                    "battery_reader_executable": self.battery_reader.executable,
                }
            ),
            "counts": {
                **self.state.counts,
                "frames_delivered": info["frames_delivered"],
                "source_drops": info["drop_counts"],
                "power_samples": self.power_log.lines,
            },
            "display": {"enabled": not self.config.no_display, "error": self.display_error},
            "threads_not_joined": [t.name for t in self.threads if t.is_alive()],
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "opencv": cv2.__version__,
                "numpy": np.__version__,
            },
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    config = parse_args(argv)
    try:
        result = BaselineRun(config, argv=argv).run()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    m = result.manifest
    counts = m.get("counts", {})
    print(
        f"run_dir={result.run_dir} end={m.get('run_end_reason')} exit={result.exit_code} "
        f"requests={counts.get('requests', 0)} skipped_busy={counts.get('tick_skipped_busy', 0)} "
        f"duration_s={(m.get('times') or {}).get('observed_duration_s')}"
    )
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
