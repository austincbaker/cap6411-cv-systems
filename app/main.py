"""Fixed-interval baseline application (item 1d).

    python -m app.main --source replay --video clip.mp4 --interval-s 2 --no-display
    python -m app.main --source webcam --device 0 --interval-s 2 --duration-s 60

Every ``--interval-s`` seconds (ticks at ``t0 + k * interval`` on the monotonic
clock, no drift) the newest source frame is sent to the VLM. At most one
request is in flight. A tick that fires while a request is still running is
skipped and logged as ``tick_skipped_busy`` with the frame ID it would have
sent; nothing is queued. Source acquisition runs on its own thread, so slow
inference never slows or pauses capture/replay.

Run directory (``--run-dir``, default ``runs/<UTC time>_<source>/``):

- ``requests.jsonl``  one line per request (frame identity, source time,
  host request start / response-available times, status, text or error type)
- ``drops.jsonl``     skipped ticks and frames the source dropped, with IDs and reasons
- ``telemetry.jsonl`` power/energy samples from the telemetry monitor
- ``manifest.json``   config, source metadata, end reasons, counts, platform

All ``host_*`` times are ``time.monotonic()`` seconds in this process;
``source_time_s`` is media-relative (None for webcam). Field names are
provisional until item 2d (#10) freezes them (``schema_version``).

Exit codes: 0 completed (EOF, --duration-s, or 'q' in the window), 2 bad
config / source failed to open / source ended in error, 130 interrupted,
1 unexpected application error.

The VLM client (#1) and telemetry monitor (#2) are not implemented yet; the
``InferenceClient`` and ``TelemetryMonitor`` protocols below define what this
app expects, and ``--vlm fake`` / ``--telemetry fake`` use test doubles from
``tests/fakes`` (run from the repository root).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import queue
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence

import cv2
import numpy as np

from app.state import ObservationState, render_overlay
from src.capture import EndReason, Frame, ReplaySource, SourceBase, SourceOpenError, WebcamSource

SCHEMA_VERSION = "0-provisional"
WINDOW_NAME = "cap6411 baseline"
FAKE_OUTCOMES = ("ok", "timeout", "connection_error", "http_error", "malformed", "empty", "ok_blank", "raise")


# ============================================================================ interfaces
# Austin's real implementations (#1 src/vlm/client.py, #2 src/energy/monitor.py)
# only need to match these shapes; nothing has to inherit from them.


@dataclass
class InferenceResult:
    """What ``InferenceClient.describe`` returns.

    status: "ok" | "timeout" | "connection_error" | "http_error" | "malformed" | "empty".
    The app adds "client_exception" (describe raised) and "abandoned_at_shutdown".
    usage stays None when the server reports no token/timing statistics.
    """

    status: str
    text: Optional[str] = None
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    usage: Optional[dict] = None


class InferenceClient(Protocol):
    def describe(
        self, *, image_jpeg: bytes, prompt: str, max_tokens: int, frame_id: int, request_id: str
    ) -> InferenceResult: ...

    def close(self) -> None: ...


class TelemetryMonitor(Protocol):
    """``sample()`` returns one dict per sensor reading, e.g.
    {sensor_id, domain, quantity, raw_value, raw_unit, value, unit, host_time_s, valid, error}.
    An unavailable sensor reports valid=False with value None, never 0."""

    def metadata(self) -> dict: ...

    def sample(self) -> list[dict]: ...

    def close(self) -> None: ...


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
    )
    src = parser.add_argument_group("source")
    src.add_argument("--source", choices=("webcam", "replay"), required=True)
    src.add_argument("--video", help="video file for --source replay")
    src.add_argument("--device", default="0", help="camera index or device path for --source webcam (default 0)")
    src.add_argument("--width", type=positive_int, help="requested camera width (observed value is recorded)")
    src.add_argument("--height", type=positive_int, help="requested camera height (observed value is recorded)")
    src.add_argument("--camera-fps", type=positive_float, help="requested camera fps (observed value is recorded)")

    sched = parser.add_argument_group("schedule")
    sched.add_argument("--interval-s", type=positive_float, default=2.0, help="seconds between VLM invocations (default 2)")
    sched.add_argument("--duration-s", type=positive_float, help="stop after this many seconds (default: until EOF / q / Ctrl-C)")

    req = parser.add_argument_group("request")
    req.add_argument("--prompt", default="Describe the scene in one short sentence.")
    req.add_argument("--max-tokens", type=positive_int, default=64)
    req.add_argument("--request-timeout-s", type=positive_float, default=30.0)
    req.add_argument("--jpeg-quality", type=int, choices=range(1, 101), metavar="1-100", default=85)
    req.add_argument("--max-image-side", type=int, default=0, help="downscale so the longer side is at most N px (0 = no resize)")

    back = parser.add_argument_group("backends")
    back.add_argument("--vlm", choices=("fake", "real"), default="fake", help="'real' requires #1 (src/vlm/client.py)")
    back.add_argument("--telemetry", choices=("fake", "real", "off"), default="fake", help="'real' requires #2 (src/energy/monitor.py)")
    back.add_argument("--telemetry-interval-s", type=positive_float, default=0.5)
    back.add_argument("--fake-vlm-latency-s", type=nonnegative_float, default=0.5, help="fake client latency per request")
    back.add_argument(
        "--fake-vlm-outcomes",
        default="ok",
        help=f"comma-separated outcomes the fake client cycles through: {','.join(FAKE_OUTCOMES)}",
    )

    out = parser.add_argument_group("output")
    out.add_argument("--run-dir", help="output directory (default runs/<UTC time>_<source>/); must not already contain files")
    out.add_argument("--no-display", action="store_true", help="headless: no OpenCV window")
    out.add_argument("--shutdown-timeout-s", type=nonnegative_float, default=5.0, help="max wait for threads/in-flight request when interrupted")
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source == "replay" and not args.video:
        parser.error("--source replay requires --video PATH")
    if args.source == "webcam" and args.video:
        parser.error("--video is only valid with --source replay")
    if args.max_image_side < 0:
        parser.error("--max-image-side must be >= 0")
    outcomes = [o.strip() for o in args.fake_vlm_outcomes.split(",") if o.strip()]
    unknown = sorted(set(outcomes) - set(FAKE_OUTCOMES))
    if not outcomes or unknown:
        parser.error(f"--fake-vlm-outcomes: unknown outcome(s) {unknown}; choose from {','.join(FAKE_OUTCOMES)}")
    args.fake_vlm_outcomes = outcomes
    return args


# ============================================================================ builders


def build_source(config: argparse.Namespace, on_drop) -> SourceBase:
    if config.source == "replay":
        return ReplaySource(config.video, on_drop=on_drop)
    return WebcamSource(
        config.device, width=config.width, height=config.height, fps=config.camera_fps, on_drop=on_drop
    )


def build_client(config: argparse.Namespace) -> InferenceClient:
    if config.vlm == "real":
        raise ConfigError("--vlm real is pending #1 (src/vlm/client.py has not landed); use --vlm fake")
    try:
        from tests.fakes.fake_vlm import FakeVLMClient
    except ImportError as exc:
        raise ConfigError(f"--vlm fake needs tests/fakes on the import path; run from the repo root ({exc})")
    return FakeVLMClient(
        latency_s=config.fake_vlm_latency_s,
        outcomes=config.fake_vlm_outcomes,
        timeout_s=config.request_timeout_s,
    )


def build_telemetry(config: argparse.Namespace) -> Optional[TelemetryMonitor]:
    if config.telemetry == "off":
        return None
    if config.telemetry == "real":
        raise ConfigError("--telemetry real is pending #2 (src/energy/monitor.py has not landed); use fake or off")
    try:
        from tests.fakes.fake_telemetry import FakeTelemetry
    except ImportError as exc:
        raise ConfigError(f"--telemetry fake needs tests/fakes on the import path; run from the repo root ({exc})")
    return FakeTelemetry()


# ============================================================================ plumbing


class JsonlWriter:
    """Thread-safe append-only JSONL file, flushed per line so interrupted runs keep their records."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._file = open(path, "a", encoding="utf-8")
        self.lines = 0

    def write(self, record: dict) -> None:
        line = json.dumps(record, default=_json_default)
        with self._lock:
            if self._file.closed:
                return
            self._file.write(line + "\n")
            self._file.flush()
            self.lines += 1

    def close(self) -> None:
        with self._lock:
            self._file.close()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    return str(value)


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


def encode_jpeg(image: np.ndarray, quality: int, max_side: int) -> tuple[bytes, int, int]:
    height, width = image.shape[:2]
    if max_side and max(height, width) > max_side:
        scale = max_side / float(max(height, width))
        image = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA)
        height, width = image.shape[:2]
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buffer.tobytes(), width, height


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
        client: Optional[InferenceClient] = None,
        telemetry: Optional[TelemetryMonitor] = None,
        argv: Optional[Sequence[str]] = None,
    ) -> None:
        self.config = config
        self.argv = list(argv) if argv is not None else None
        # Build backends before touching the filesystem so config errors leave nothing behind.
        self.client = client if client is not None else build_client(config)
        self.telemetry = telemetry if telemetry is not None or config.telemetry == "off" else build_telemetry(config)
        self.run_dir = prepare_run_dir(config)
        self.requests_log = JsonlWriter(self.run_dir / "requests.jsonl")
        self.drops_log = JsonlWriter(self.run_dir / "drops.jsonl")
        self.telemetry_log = JsonlWriter(self.run_dir / "telemetry.jsonl")
        # source_factory(on_drop) lets tests inject a source wired to this run's drop log.
        factory = source_factory or (lambda on_drop: build_source(config, on_drop))
        self.source = factory(self._on_source_drop)
        self.state = ObservationState()
        self.slot = LatestFrameSlot()
        self.jobs: "queue.Queue[Optional[tuple]]" = queue.Queue(maxsize=1)
        self.results: "queue.Queue[dict]" = queue.Queue()
        self.telemetry_stop = threading.Event()
        self.threads: list[threading.Thread] = []
        self.in_flight: Optional[dict] = None
        self.display_enabled = not config.no_display
        self.display_note: Optional[str] = None
        self.display_used = False
        self.run_end_reason: Optional[str] = None
        self.error_detail: Optional[str] = None
        self.manifest: dict = {}
        self.times: dict[str, Optional[float]] = {
            "host_run_start_s": None,
            "host_first_frame_s": None,
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
        self._spawn("capture", self._capture_loop)
        self._spawn("inference", self._inference_loop)
        if self.telemetry is not None:
            self._spawn("telemetry", self._telemetry_loop)

    def _spawn(self, name: str, target: Callable[[], None]) -> None:
        # daemon=True only as a last resort if a client ignores its timeout; shutdown always joins.
        thread = threading.Thread(target=target, name=f"baseline-{name}", daemon=True)
        self.threads.append(thread)
        thread.start()

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

    def _execute(self, frame: Frame, request_id: str, tick_index: int, host_tick_s: float) -> dict:
        record = {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "tick_index": tick_index,
            "frame_id": frame.frame_id,
            "source_kind": frame.source_kind,
            "source_time_s": frame.source_time_s,
            "host_capture_s": frame.host_capture_s,
            "host_tick_s": host_tick_s,
        }
        encode_start = time.monotonic()
        try:
            jpeg, width, height = encode_jpeg(frame.image, self.config.jpeg_quality, self.config.max_image_side)
        except Exception as exc:
            now = time.monotonic()
            record.update(
                host_request_start_s=None, host_response_available_s=now, duration_s=None,
                encode_s=now - encode_start, image_bytes=None, image_width=None, image_height=None,
                status="encode_error", text=None, error_type=type(exc).__name__, error_detail=str(exc), usage=None,
            )
            return record
        host_request_start_s = time.monotonic()
        try:
            result = self.client.describe(
                image_jpeg=jpeg,
                prompt=self.config.prompt,
                max_tokens=self.config.max_tokens,
                frame_id=frame.frame_id,
                request_id=request_id,
            )
            status = str(getattr(result, "status", None))
            text = getattr(result, "text", None)
            error_type = getattr(result, "error_type", None)
            error_detail = getattr(result, "error_detail", None)
            usage = getattr(result, "usage", None)
        except Exception as exc:
            status, text, usage = "client_exception", None, None
            error_type, error_detail = type(exc).__name__, str(exc)
        host_response_available_s = time.monotonic()
        if status == "ok" and not (isinstance(text, str) and text.strip()):
            status, error_type, error_detail = "empty", error_type or "blank_text", "status ok but no text"
        record.update(
            host_request_start_s=host_request_start_s,
            host_response_available_s=host_response_available_s,
            duration_s=host_response_available_s - host_request_start_s,
            encode_s=host_request_start_s - encode_start,
            image_bytes=len(jpeg),
            image_width=width,
            image_height=height,
            status=status,
            text=text if status == "ok" else None,
            error_type=None if status == "ok" else (error_type or status),
            error_detail=None if status == "ok" else error_detail,
            usage=usage,
        )
        return record

    def _telemetry_loop(self) -> None:
        interval = self.config.telemetry_interval_s
        next_t = time.monotonic()
        while not self.telemetry_stop.is_set():
            try:
                samples = list(self.telemetry.sample())
            except Exception as exc:
                samples = [{"valid": False, "value": None, "error": f"{type(exc).__name__}: {exc}", "host_time_s": time.monotonic()}]
            for sample in samples:
                self.telemetry_log.write({"schema_version": SCHEMA_VERSION, **sample})
            next_t += interval
            self.telemetry_stop.wait(max(0.0, next_t - time.monotonic()))

    # -- logging -----------------------------------------------------------
    def _on_source_drop(self, frame_id: int, reason: str, host_time_s: float, detail: str = "") -> None:
        # Called on the capture thread.
        self.drops_log.write({
            "schema_version": SCHEMA_VERSION, "origin": "source", "reason": reason,
            "frame_id": frame_id, "host_time_s": host_time_s, "detail": detail,
        })

    def _log_tick_drop(self, reason: str, tick_index: int, host_tick_s: float, frame: Optional[Frame], **extra: Any) -> None:
        self.state.bump(reason)
        self.drops_log.write({
            "schema_version": SCHEMA_VERSION, "origin": "app", "reason": reason,
            "tick_index": tick_index, "host_tick_s": host_tick_s, "host_time_s": time.monotonic(),
            "frame_id": frame.frame_id if frame else None,
            "source_time_s": frame.source_time_s if frame else None,
            **extra,
        })

    def _handle_result(self, record: dict) -> None:
        self.requests_log.write(record)
        self.state.record_result(
            status=record["status"], text=record["text"], error_type=record["error_type"],
            request_id=record["request_id"], frame_id=record["frame_id"],
            source_time_s=record["source_time_s"], host_capture_s=record["host_capture_s"],
            host_response_available_s=record["host_response_available_s"],
        )
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
        self.times["host_first_frame_s"] = self.slot.latest().host_capture_s
        self.times["host_tick_origin_s"] = tick_origin
        end_at = tick_origin + self.config.duration_s if self.config.duration_s else None
        tick_index = 0
        next_tick = tick_origin
        last_sent_frame_id: Optional[int] = None
        last_draw = -1.0

        while True:
            self._drain_results()
            now = time.monotonic()
            if end_at is not None and now >= end_at and not self.slot.closed.is_set():
                self.source.stop(EndReason.DURATION_LIMIT)
            if self.slot.closed.is_set():
                return  # no dispatch after the source ends; shutdown collects any in-flight request

            if now >= next_tick:
                frame = self.slot.latest()
                if self.in_flight is not None:
                    self._log_tick_drop(
                        "tick_skipped_busy", tick_index, next_tick, frame,
                        in_flight_request_id=self.in_flight["request_id"],
                        in_flight_frame_id=self.in_flight["frame_id"],
                    )
                elif frame.frame_id == last_sent_frame_id:
                    self._log_tick_drop("tick_skipped_no_new_frame", tick_index, next_tick, frame)
                else:
                    request_id = uuid.uuid4().hex[:12]
                    self.in_flight = {"request_id": request_id, "frame_id": frame.frame_id}
                    self.state.record_dispatch(frame.frame_id)
                    self.jobs.put_nowait((frame, request_id, tick_index, next_tick))
                    last_sent_frame_id = frame.frame_id
                tick_index += 1
                next_tick = tick_origin + tick_index * interval
                while next_tick <= now:  # the loop itself stalled past whole ticks
                    self._log_tick_drop("tick_missed_loop_stall", tick_index, next_tick, None)
                    tick_index += 1
                    next_tick = tick_origin + tick_index * interval

            if self.display_enabled and now - last_draw >= 1 / 30:
                last_draw = now
                self._draw()

            wait = max(0.0, min(next_tick - time.monotonic(), 0.02 if self.display_enabled else 0.05))
            self._drain_results(timeout=wait)

    def _draw(self) -> None:
        frame = self.slot.latest()
        if frame is None:
            return
        self.display_used = True
        try:
            cv2.imshow(WINDOW_NAME, render_overlay(frame.image, self.state.overlay_lines(time.monotonic())))
            key = cv2.waitKey(1) & 0xFF
        except cv2.error as exc:
            self.display_enabled = False
            self.display_note = f"display disabled: {exc}".strip()
            print(f"warning: {self.display_note}; continuing headless", file=sys.stderr)
            return
        if key in (ord("q"), 27):
            self.run_end_reason = "user_quit"
            self.source.stop(EndReason.STOPPED)

    # -- shutdown ----------------------------------------------------------
    def _exit_code_for_source_end(self) -> int:
        if self.slot.error is not None:
            self.run_end_reason = "capture_error"
            self.error_detail = f"{type(self.slot.error).__name__}: {self.slot.error}"
            return 1
        end = self.source.end
        if self.run_end_reason == "user_quit":
            return 0
        if end is None:
            self.run_end_reason = "source_ended_without_reason"
            return 1
        self.run_end_reason = end.reason.value
        return 2 if end.reason.is_error else 0

    def _finalize(self, exit_code: int, *, interrupted: bool) -> RunResult:
        grace = self.config.shutdown_timeout_s
        if not self.source.end:
            self.source.stop(EndReason.INTERRUPTED if interrupted else EndReason.STOPPED)
        if interrupted:
            self._close_client()  # ask the client to abandon the in-flight request
        capture_threads = [t for t in self.threads if t.name == "baseline-capture"]
        for thread in capture_threads:
            thread.join(grace)
        if not any(t.is_alive() for t in capture_threads):
            self.source.close()  # normally already closed by the capture thread's `with`

        if self.in_flight is not None:
            wait = grace if interrupted else self.config.request_timeout_s + grace
            deadline = time.monotonic() + wait
            while self.in_flight is not None and time.monotonic() < deadline:
                self._drain_results(timeout=min(0.05, max(0.0, deadline - time.monotonic())))
        if self.in_flight is not None:
            self.requests_log.write({
                "schema_version": SCHEMA_VERSION, **self.in_flight, "status": "abandoned_at_shutdown",
                "host_response_available_s": None, "text": None, "error_type": "abandoned_at_shutdown",
            })
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
        if self.telemetry is not None:
            try:
                self.telemetry.close()
            except Exception:
                pass
        if self.display_used:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except cv2.error:
                pass

        self.times["host_run_end_s"] = time.monotonic()
        self.manifest = self._build_manifest(exit_code)
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, default=_json_default) + "\n")
        for log in (self.requests_log, self.drops_log, self.telemetry_log):
            log.close()
        return RunResult(exit_code=exit_code, run_dir=self.run_dir, manifest=self.manifest)

    def _close_client(self) -> None:
        if getattr(self, "_client_closed", False):
            return
        self._client_closed = True
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
            "run_dir": str(self.run_dir),
            "argv": self.argv,
            "config": {k: v for k, v in vars(self.config).items()},
            "started_wall_utc": self.started_wall_utc,
            "time_bases": {
                "host_*": "time.monotonic() seconds in this process",
                "source_time_s": "media-relative seconds (replay); null for webcam",
            },
            "times": {**self.times, "observed_duration_s": (end - start) if start is not None and end is not None else None},
            "run_end_reason": self.run_end_reason,
            "exit_code": exit_code,
            "error_detail": self.error_detail,
            "source": {"info": info, "end": self.source.end.as_dict() if self.source.end else None},
            "vlm": {"kind": self.config.vlm, "metadata": _safe_metadata(self.client)},
            "telemetry": (
                {"kind": "off"} if self.telemetry is None
                else {"kind": self.config.telemetry, "interval_s": self.config.telemetry_interval_s, "metadata": _safe_metadata(self.telemetry)}
            ),
            "counts": {
                **self.state.counts,
                "frames_delivered": info["frames_delivered"],
                "source_drops": info["drop_counts"],
                "requests_logged": self.requests_log.lines,
                "drops_logged": self.drops_log.lines,
                "telemetry_samples_logged": self.telemetry_log.lines,
            },
            "display": {"enabled": not self.config.no_display, "note": self.display_note},
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


def _safe_metadata(obj: Any) -> Optional[dict]:
    meta = getattr(obj, "metadata", None)
    if not callable(meta):
        return None
    try:
        return meta()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


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
