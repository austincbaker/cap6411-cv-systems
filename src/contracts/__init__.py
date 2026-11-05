"""Shared validator for the item 2d file contracts (``docs/data-contracts.md``).

The application, the event scorer (3d) and the energy analyzer (3g) import this
module instead of re-parsing run files. It checks field presence, types,
missing-value rules and a few cross-field rules; it does not score events or
integrate energy.

    from contracts import read_artifact, validate_run_dir

    records, issues = read_artifact("power", run_dir / "power.csv")
    issues = validate_run_dir(run_dir)

Missing values are ``null`` in JSON and an empty cell in CSV, never ``0``.
CSV booleans are ``true``/``false``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

CONTRACT_VERSION = "1-draft"

REQUEST_STATUSES = frozenset(
    {
        "ok",
        "timeout",
        "connection_error",
        "transport_error",
        "http_error",
        "invalid_response",
        "empty_response",
        "client_exception",
        "abandoned_at_shutdown",
    }
)
SCHEDULE_ORIGINS = frozenset({"app", "source", "gate"})
POWER_SOURCES = frozenset({"windows_battery", "sysfs", "telemetry_error"})
SPLITS = frozenset({"dev", "validation", "test"})
# Provisional until item 1e (#5) fixes the event vocabulary.
EVENT_LABELS = frozenset({"person_enters", "person_leaves", "object_placed", "object_removed"})

RUN_FILES = {
    "manifest": "manifest.json",
    "request": "requests.jsonl",
    "schedule": "drops.jsonl",
    "power": "power.csv",
}


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # str | int | float | bool | dict | list | any
    required: bool = True
    nullable: bool = False
    choices: frozenset[str] | None = None


@dataclass(frozen=True)
class Issue:
    artifact: str
    location: str  # file path plus line, or "<record>"
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def _f(name: str, kind: str, *, opt: bool = False, null: bool = False, choices=None) -> Field:
    return Field(name, kind, not opt, null, frozenset(choices) if choices else None)


SCHEMAS: dict[str, tuple[Field, ...]] = {
    "manifest": (
        _f("schema_version", "str"),
        _f("run_id", "str"),
        _f("policy", "str"),
        _f("run_dir", "str"),
        _f("argv", "list", null=True),
        _f("config", "dict"),
        _f("started_wall_utc", "str"),
        _f("times", "dict"),
        _f("run_end_reason", "str"),
        _f("exit_code", "int"),
        _f("error_detail", "str", null=True),
        _f("files", "dict"),
        _f("source", "dict"),
        _f("vlm", "dict"),
        _f("telemetry", "dict"),
        _f("power_state", "dict"),
        _f("counts", "dict"),
        _f("platform", "dict"),
    ),
    "request": (
        _f("schema_version", "str"),
        _f("run_id", "str"),
        _f("request_id", "str", null=True),
        _f("tick_index", "int"),
        _f("frame_id", "int"),
        _f("source_kind", "str", choices={"replay", "webcam"}),
        _f("source_time_s", "float", null=True),
        _f("host_capture_s", "float"),
        _f("host_tick_s", "float"),
        _f("request_started_s", "float"),
        _f("response_available_s", "float", null=True),
        _f("status", "str", choices=REQUEST_STATUSES),
        _f("text", "str", null=True),
        _f("error", "str", null=True),
        _f("server_state_unknown", "bool"),
        _f("elapsed_s", "float", opt=True, null=True),
        _f("model", "str", opt=True, null=True),
        _f("max_output_tokens", "int", opt=True, null=True),
        _f("prompt_tokens", "int", opt=True, null=True),
        _f("output_tokens", "int", opt=True, null=True),
        _f("cached_tokens", "int", opt=True, null=True),
        _f("finish_reason", "str", opt=True, null=True),
        _f("http_status", "int", opt=True, null=True),
        _f("encode_s", "float", opt=True, null=True),
        _f("image_bytes", "int", opt=True, null=True),
    ),
    "schedule": (
        _f("schema_version", "str"),
        _f("run_id", "str"),
        _f("origin", "str", choices=SCHEDULE_ORIGINS),
        _f("reason", "str"),
        _f("frame_id", "int", null=True),
        _f("host_time_s", "float"),
        _f("tick_index", "int", opt=True, null=True),
        _f("host_tick_s", "float", opt=True, null=True),
        _f("source_time_s", "float", opt=True, null=True),
        _f("in_flight_frame_id", "int", opt=True, null=True),
        _f("detail", "str", opt=True, null=True),
    ),
    "power": (
        _f("schema_version", "str"),
        _f("run_id", "str"),
        _f("source", "str", choices=POWER_SOURCES),
        _f("sensor_id", "str"),
        _f("domain", "str"),
        _f("quantity", "str"),
        _f("host_read_start_s", "float", null=True),
        _f("host_time_s", "float"),
        _f("raw_value", "float", null=True),
        _f("raw_unit", "str", null=True),
        _f("value", "float", null=True),
        _f("unit", "str", null=True),
        _f("valid", "bool"),
        _f("error", "str", null=True),
        _f("ac_online", "bool", null=True),
        _f("battery_status", "str", null=True),
        _f("quality_flags", "str", null=True),
    ),
    "annotation": (
        _f("schema_version", "str"),
        _f("video_id", "str"),
        _f("event_id", "str"),
        _f("label", "str", choices=EVENT_LABELS),
        _f("onset_s", "float"),
        _f("end_s", "float", null=True),
        _f("group_id", "str"),
        _f("split", "str", null=True, choices=SPLITS),
        _f("annotator", "str", null=True),
        _f("notes", "str", null=True),
    ),
    "prediction": (
        _f("schema_version", "str"),
        _f("run_id", "str"),
        _f("prediction_id", "str"),
        _f("label", "str"),
        _f("request_id", "str"),
        _f("frame_id", "int"),
        _f("source_time_s", "float", null=True),
        _f("host_capture_s", "float"),
        _f("response_available_s", "float"),
        _f("available_source_time_s", "float", null=True),
        _f("observation", "any", opt=True, null=True),
    ),
    "metrics": (
        _f("schema_version", "str"),
        _f("run_id", "str"),
        _f("video_id", "str", null=True),
        _f("scorer", "dict"),
        _f("matching", "dict"),
        _f("counts", "dict"),
        _f("precision", "float", null=True),
        _f("recall", "float", null=True),
        _f("f1", "float", null=True),
        _f("delay_s", "dict"),
        _f("matches", "list"),
        _f("energy", "list"),
        _f("errors", "list"),
    ),
}

CSV_KINDS = frozenset({"power", "annotation"})
POWER_COLUMNS = [f.name for f in SCHEMAS["power"]]
ANNOTATION_COLUMNS = [f.name for f in SCHEMAS["annotation"]]
METRIC_COUNT_KEYS = (
    "events",
    "predictions",
    "true_positives",
    "false_positives",
    "false_negatives",
)
ENERGY_DOMAINS = frozenset({"whole_laptop_battery", "cpu_package"})


# ---------------------------------------------------------------------------- types


def _is_kind(value: Any, kind: str) -> bool:
    if kind == "any":
        return True
    if kind == "str":
        return isinstance(value, str)
    if kind == "int":
        return type(value) is int
    if kind == "float":
        return type(value) in (int, float) and math.isfinite(value)
    if kind == "bool":
        return type(value) is bool
    if kind == "dict":
        return isinstance(value, dict)
    if kind == "list":
        return isinstance(value, list)
    raise ValueError(f"unknown field kind {kind!r}")


def _parse_cell(text: str, kind: str) -> Any:
    """Convert one CSV cell; an empty cell is missing (None). Raises ValueError."""
    if text == "":
        return None
    if kind == "str":
        return text
    if kind == "bool":
        if text not in ("true", "false"):
            raise ValueError(f"expected true/false, got {text!r}")
        return text == "true"
    if kind == "int":
        return int(text)
    if kind == "float":
        value = float(text)
        if not math.isfinite(value):
            raise ValueError(f"nonfinite number {text!r}")
        return value
    raise ValueError(f"field kind {kind!r} cannot come from CSV")


def format_cell(value: Any) -> str:
    """Write one CSV cell in contract form (used by producers)."""
    if value is None:
        return ""
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


# ---------------------------------------------------------------------------- records


def validate_record(kind: str, record: Any) -> list[str]:
    """Return problems with one record; an empty list means it conforms."""
    if kind not in SCHEMAS:
        raise ValueError(f"unknown artifact kind {kind!r}")
    if not isinstance(record, dict):
        return ["record is not an object"]
    problems = []
    for spec in SCHEMAS[kind]:
        if spec.name not in record:
            if spec.required:
                problems.append(f"missing field {spec.name!r}")
            continue
        value = record[spec.name]
        if value is None:
            if not spec.nullable:
                problems.append(f"{spec.name!r} must not be missing")
            continue
        if not _is_kind(value, spec.kind):
            problems.append(f"{spec.name!r} must be {spec.kind}, got {type(value).__name__}")
        elif spec.choices is not None and value not in spec.choices:
            problems.append(f"{spec.name!r} value {value!r} is not one of {sorted(spec.choices)}")
    version = record.get("schema_version")
    if version is not None and version != CONTRACT_VERSION:
        problems.append(f"schema_version {version!r} is not {CONTRACT_VERSION!r}")
    if not problems:
        problems.extend(_RULES.get(kind, lambda r: [])(record))
    return problems


def _request_rules(r: dict) -> list[str]:
    out = []
    if r["status"] == "ok":
        if not r.get("text"):
            out.append("status 'ok' needs nonempty text")
        if r["response_available_s"] is None:
            out.append("status 'ok' needs response_available_s")
    elif not r.get("error"):
        out.append(f"status {r['status']!r} needs an error")
    if r["status"] == "abandoned_at_shutdown" and r["response_available_s"] is not None:
        out.append("abandoned_at_shutdown has no response_available_s")
    end = r["response_available_s"]
    if end is not None and end < r["request_started_s"]:
        out.append("response_available_s is before request_started_s")
    return out


def _power_rules(r: dict) -> list[str]:
    out = []
    if r["valid"]:
        if r["value"] is None or r["unit"] is None:
            out.append("a valid sample needs value and unit")
        if r["error"]:
            out.append("a valid sample has no error")
    else:
        if r["value"] is not None:
            out.append("an invalid sample must leave value missing, not filled")
        if not r["error"]:
            out.append("an invalid sample needs an error")
    start = r["host_read_start_s"]
    if start is not None and start > r["host_time_s"]:
        out.append("host_read_start_s is after host_time_s")
    return out


def _annotation_rules(r: dict) -> list[str]:
    out = []
    if r["onset_s"] < 0:
        out.append("onset_s is negative")
    if r["end_s"] is not None and r["end_s"] < r["onset_s"]:
        out.append("end_s is before onset_s")
    return out


def _prediction_rules(r: dict) -> list[str]:
    out = []
    if r["response_available_s"] < r["host_capture_s"]:
        out.append("response_available_s is before host_capture_s")
    src, avail = r["source_time_s"], r["available_source_time_s"]
    if (src is None) != (avail is None):
        out.append("source_time_s and available_source_time_s are both set or both missing")
    elif src is not None and avail < src:
        out.append("available_source_time_s is before source_time_s")
    if src is not None and avail is not None:
        expected = src + (r["response_available_s"] - r["host_capture_s"])
        if not math.isclose(avail, expected, rel_tol=0.0, abs_tol=1e-6):
            out.append("available_source_time_s does not match host response delay")
    return out


def _metrics_rules(r: dict) -> list[str]:
    out = []
    counts = r["counts"]
    for key in METRIC_COUNT_KEYS:
        if type(counts.get(key)) is not int or counts[key] < 0:
            out.append(f"counts.{key} must be a nonnegative integer")
    for name in ("precision", "recall", "f1"):
        value = r[name]
        if value is not None and not 0 <= value <= 1:
            out.append(f"{name} must be within [0, 1]")
    for i, entry in enumerate(r["energy"]):
        if not isinstance(entry, dict):
            out.append(f"energy[{i}] is not an object")
            continue
        if entry.get("domain") not in ENERGY_DOMAINS:
            out.append(f"energy[{i}].domain must be one of {sorted(ENERGY_DOMAINS)}")
        has_value = entry.get("energy_j") is not None
        if has_value == bool(entry.get("unavailable_reason")):
            out.append(f"energy[{i}] needs energy_j or unavailable_reason, not both")
    for i, err in enumerate(r["errors"]):
        if not isinstance(err, dict) or not isinstance(err.get("code"), str):
            out.append(f"errors[{i}] needs a string code")
    return out


def _manifest_rules(r: dict) -> list[str]:
    out = []
    for key in ("host_run_start_s", "host_tick_origin_s", "host_run_end_s"):
        if key not in r["times"]:
            out.append(f"times.{key} is missing (use null when unknown)")
        elif r["times"][key] is not None and not _is_kind(r["times"][key], "float"):
            out.append(f"times.{key} must be a finite number or null")
    times = [
        r["times"].get(key) for key in ("host_run_start_s", "host_tick_origin_s", "host_run_end_s")
    ]
    known = [value for value in times if value is not None and _is_kind(value, "float")]
    if known != sorted(known):
        out.append("manifest host times are out of order")
    if "enabled" not in r["telemetry"]:
        out.append("telemetry.enabled is missing")
    for key in ("at_start", "at_end"):
        if key not in r["power_state"]:
            out.append(f"power_state.{key} is missing (use null when unknown)")
    return out


_RULES = {
    "request": _request_rules,
    "power": _power_rules,
    "annotation": _annotation_rules,
    "prediction": _prediction_rules,
    "metrics": _metrics_rules,
    "manifest": _manifest_rules,
}


# ---------------------------------------------------------------------------- files


def read_artifact(kind: str, path: Path | str) -> tuple[list[dict], list[Issue]]:
    """Parse one artifact file into typed records plus every contract issue found.

    JSON kinds (``manifest``, ``metrics``) return a one-element list. Records
    that fail validation are still returned so callers can report them.
    """
    path = Path(path)
    issues: list[Issue] = []
    records: list[dict] = []

    def issue(where: str, message: str) -> None:
        issues.append(Issue(kind, where, message))

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        issue(str(path), f"cannot read: {exc}")
        return records, issues

    if kind in CSV_KINDS:
        specs = {f.name: f for f in SCHEMAS[kind]}
        reader = csv.DictReader(text.splitlines())
        header = reader.fieldnames or []
        missing = [n for n in specs if specs[n].required and n not in header]
        if missing:
            issue(f"{path}:1", f"missing columns {missing}")
            return records, issues
        for line_no, row in enumerate(reader, start=2):
            where = f"{path}:{line_no}"
            record: dict[str, Any] = {}
            bad = False
            for name, cell in row.items():
                if name is None or name not in specs:
                    continue
                try:
                    record[name] = _parse_cell(cell or "", specs[name].kind)
                except ValueError as exc:
                    issue(where, f"{name}: {exc}")
                    bad = True
            records.append(record)
            if not bad:
                for problem in validate_record(kind, record):
                    issue(where, problem)
    elif kind in ("manifest", "metrics"):
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            issue(str(path), f"invalid JSON: {exc}")
            return records, issues
        records.append(record)
        for problem in validate_record(kind, record):
            issue(str(path), problem)
    else:
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            where = f"{path}:{line_no}"
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issue(where, f"invalid JSON: {exc}")
                continue
            records.append(record)
            for problem in validate_record(kind, record):
                issue(where, problem)
    return records, issues


def validate_run_dir(run_dir: Path | str) -> list[Issue]:
    """Validate an application run directory, including cross-file run IDs."""
    run_dir = Path(run_dir)
    issues: list[Issue] = []
    loaded: dict[str, list[dict]] = {}
    for kind, name in RUN_FILES.items():
        records, found = read_artifact(kind, run_dir / name)
        loaded[kind] = records
        issues.extend(found)
    manifest = loaded["manifest"][0] if loaded["manifest"] else None
    if not isinstance(manifest, dict):
        return issues
    run_id = manifest.get("run_id")
    for kind in ("request", "schedule", "power"):
        for i, record in enumerate(loaded[kind]):
            if isinstance(record, dict) and record.get("run_id") != run_id:
                issues.append(
                    Issue(kind, f"{run_dir / RUN_FILES[kind]}[{i}]", "run_id differs from manifest")
                )
    predictions = run_dir / "predictions.jsonl"
    if predictions.exists():
        records, found = read_artifact("prediction", predictions)
        issues.extend(found)
        request_ids = {r.get("request_id") for r in loaded["request"] if isinstance(r, dict)}
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            if record.get("run_id") != run_id:
                issues.append(Issue("prediction", f"{predictions}[{i}]", "run_id differs"))
            if record.get("request_id") not in request_ids:
                issues.append(
                    Issue("prediction", f"{predictions}[{i}]", "request_id not in requests.jsonl")
                )
    return issues


def csv_row(kind: str, record: dict) -> list[str]:
    """Format a record as one CSV row in the contract's column order."""
    return [format_cell(record.get(f.name)) for f in SCHEMAS[kind]]


def main(argv: Sequence[str] | None = None) -> int:
    """``contracts-check RUN_DIR`` or ``contracts-check --kind KIND FILE``; exit 1 on issues."""
    parser = argparse.ArgumentParser(prog="contracts-check", description=main.__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--kind", choices=sorted(SCHEMAS), help="check one file of this kind")
    args = parser.parse_args(argv)
    if args.kind:
        _, issues = read_artifact(args.kind, args.path)
    else:
        issues = validate_run_dir(args.path)
    for item in issues:
        print(item)
    print(f"{len(issues)} issue(s)", file=sys.stderr)
    return 1 if issues else 0
