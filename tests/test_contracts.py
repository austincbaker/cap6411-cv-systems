"""Item 2d contract checks: every fixture validates, every malformed fixture is caught,
and the hand-scored expectations agree with the fixture data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts import (
    CONTRACT_VERSION,
    format_cell,
    main,
    read_artifact,
    validate_record,
    validate_run_dir,
)

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
RUN = FIXTURES / "run_valid"


def load(kind, path):
    records, issues = read_artifact(kind, path)
    assert [str(i) for i in issues] == []
    return records


def messages(kind, path):
    return " | ".join(i.message for i in read_artifact(kind, path)[1])


# --------------------------------------------------------------------------- valid fixtures


def test_valid_run_directory_conforms():
    assert [str(i) for i in validate_run_dir(RUN)] == []


@pytest.mark.parametrize(
    "kind,name",
    [
        ("annotation", "annotations.csv"),
        ("power", "power_ac_online.csv"),
        ("metrics", "expected_metrics.json"),
        ("metrics", "expected_metrics_ac_online.json"),
    ],
)
def test_valid_fixture_files_conform(kind, name):
    assert load(kind, FIXTURES / name)


def test_csv_missing_cells_parse_as_none_and_booleans_as_bool():
    rows = load("power", RUN / "power.csv")
    invalid = [r for r in rows if not r["valid"]]
    assert invalid and all(r["value"] is None and r["raw_value"] is None for r in invalid)
    assert all(type(r["valid"]) is bool for r in rows)
    assert [format_cell(v) for v in (None, True, False, 1.5)] == ["", "true", "false", "1.5"]


# --------------------------------------------------------------------------- malformed fixtures


def test_old_schema_version_and_missing_manifest_field_are_reported():
    text = messages("manifest", FIXTURES / "invalid" / "manifest_old_version.json")
    assert "'0-provisional' is not '1-draft'" in text
    assert "missing field 'power_state'" in text


def test_bad_request_records_are_reported_per_line():
    issues = read_artifact("request", FIXTURES / "invalid" / "requests_bad.jsonl")[1]
    by_line = {i.location.rsplit(":", 1)[1]: i.message for i in issues}
    assert "status 'ok' needs nonempty text" in by_line["1"]
    assert "missing field 'frame_id'" in by_line["2"]
    assert "status 'timeout' needs an error" in by_line["3"]
    assert "'prompt_tokens' must be int" in by_line["4"]


def test_zero_written_for_a_missing_power_value_is_rejected():
    text = messages("power", FIXTURES / "invalid" / "power_zero_for_missing.csv")
    assert "must leave value missing, not filled" in text


def test_bad_annotations_are_reported():
    text = messages("annotation", FIXTURES / "invalid" / "annotations_bad.csv")
    assert "end_s is before onset_s" in text
    assert "'cat_appears' is not one of" in text
    assert "'holdout' is not one of" in text


def test_bad_predictions_are_reported():
    text = messages("prediction", FIXTURES / "invalid" / "predictions_bad.jsonl")
    assert "available_source_time_s is before source_time_s" in text
    assert "both set or both missing" in text


def test_bad_metrics_report_is_rejected():
    text = messages("metrics", FIXTURES / "invalid" / "metrics_bad.json")
    assert "counts.false_negatives must be a nonnegative integer" in text
    assert "precision must be within [0, 1]" in text
    assert "needs energy_j or unavailable_reason, not both" in text


def test_run_dir_cross_file_checks(tmp_path):
    for path in RUN.iterdir():
        (tmp_path / path.name).write_text(path.read_text())
    lines = (tmp_path / "predictions.jsonl").read_text().splitlines()
    lines[0] = lines[0].replace('"req-0005"', '"req-9999"')
    (tmp_path / "predictions.jsonl").write_text("\n".join(lines) + "\n")
    (tmp_path / "power.csv").write_text(
        (tmp_path / "power.csv").read_text().replace("0000000000000000000000000000002d", "f" * 32)
    )
    text = " | ".join(i.message for i in validate_run_dir(tmp_path))
    assert "request_id not in requests.jsonl" in text
    assert "run_id differs from manifest" in text


def test_missing_run_file_is_an_issue_not_a_crash(tmp_path):
    (tmp_path / "manifest.json").write_text((RUN / "manifest.json").read_text())
    text = " | ".join(i.message for i in validate_run_dir(tmp_path))
    assert "cannot read" in text


@pytest.mark.parametrize(
    "record,expected",
    [
        ({"schema_version": CONTRACT_VERSION, "frame_id": True}, "'frame_id' must be int"),
        ("not a dict", "record is not an object"),
    ],
)
def test_validate_record_type_rules(record, expected):
    assert any(expected in p for p in validate_record("request", record))


def test_nonfinite_csv_number_is_rejected(tmp_path):
    rows = (RUN / "power.csv").read_text().splitlines()
    rows[1] = rows[1].replace(",16920.0,", ",nan,")
    (tmp_path / "power.csv").write_text("\n".join(rows) + "\n")
    assert "nonfinite" in messages("power", tmp_path / "power.csv")


def test_cli_exit_status(capsys):
    assert main([str(RUN)]) == 0
    assert main(["--kind", "power", str(FIXTURES / "invalid" / "power_zero_for_missing.csv")]) == 1
    assert "not filled" in capsys.readouterr().out


# --------------------------------------------------------------------------- hand-scored values


def test_predictions_trace_to_requests_and_availability_follows_the_documented_rule():
    requests = {r["request_id"]: r for r in load("request", RUN / "requests.jsonl")}
    for p in load("prediction", RUN / "predictions.jsonl"):
        r = requests[p["request_id"]]
        assert (p["frame_id"], p["source_time_s"]) == (r["frame_id"], r["source_time_s"])
        assert p["response_available_s"] == r["response_available_s"]
        latency = r["response_available_s"] - r["host_capture_s"]
        assert p["available_source_time_s"] == pytest.approx(r["source_time_s"] + latency)


def test_expected_battery_energy_matches_the_documented_rule():
    """docs/data-contracts.md "Energy rules": first and last valid stored-energy samples
    inside the measured window, only when every valid sample is on battery."""
    manifest = json.loads((RUN / "manifest.json").read_text())
    start, end = manifest["times"]["host_tick_origin_s"], manifest["times"]["host_run_end_s"]

    def battery_energy(power_csv):
        rows = [
            r
            for r in load("power", power_csv)
            if r["source"] == "windows_battery"
            and r["quantity"] == "stored_energy"
            and start <= r["host_time_s"] <= end
        ]
        valid = [r for r in rows if r["valid"]]
        if not all(r["ac_online"] is False and r["battery_status"] == "Discharging" for r in valid):
            return None, "not_on_battery", len(valid), len(rows) - len(valid)
        first, last = valid[0], valid[-1]
        span = last["host_time_s"] - first["host_time_s"]
        return (first["value"] - last["value"], span), None, len(valid), len(rows) - len(valid)

    expected = json.loads((FIXTURES / "expected_metrics.json").read_text())["energy"][0]
    (energy_j, span), reason, used, invalid = battery_energy(RUN / "power.csv")
    assert reason is None and (used, invalid) == (expected["samples_used"], 1)
    assert energy_j == pytest.approx(expected["energy_j"])
    assert span == pytest.approx(expected["sample_span_s"])
    assert energy_j / span == pytest.approx(expected["mean_power_w"])

    ac = json.loads((FIXTURES / "expected_metrics_ac_online.json").read_text())["energy"][0]
    value, reason, _, _ = battery_energy(FIXTURES / "power_ac_online.csv")
    assert value is None and reason == ac["unavailable_reason"] == "not_on_battery"


def test_expected_quality_counts_are_consistent():
    m = json.loads((FIXTURES / "expected_metrics.json").read_text())
    c = m["counts"]
    events = [
        a
        for a in load("annotation", FIXTURES / "annotations.csv")
        if a["video_id"] == m["video_id"]
    ]
    predictions = load("prediction", RUN / "predictions.jsonl")
    assert (c["events"], c["predictions"]) == (len(events), len(predictions))
    assert c["true_positives"] + c["false_negatives"] == c["events"]
    assert c["true_positives"] + c["false_positives"] == c["predictions"]
    assert c["false_positives"] == c["duplicates"] + c["late"] + c["unmatched_predictions"]
    outcomes = [x["outcome"] for x in m["matches"]]
    assert outcomes.count("true_positive") == c["true_positives"]
    assert m["precision"] == pytest.approx(c["true_positives"] / c["predictions"])
    assert m["recall"] == pytest.approx(c["true_positives"] / c["events"], abs=1e-6)
    p, r = m["precision"], m["recall"]
    assert m["f1"] == pytest.approx(2 * p * r / (p + r), abs=1e-6)
    delays = [x["delay_s"] for x in m["matches"] if x["outcome"] == "true_positive"]
    assert m["delay_s"]["mean"] == pytest.approx(sum(delays) / len(delays))


def test_prediction_rejects_incorrect_source_availability():
    record = load("prediction", RUN / "predictions.jsonl")[0]
    record["available_source_time_s"] = record["source_time_s"]
    assert any("host response delay" in issue for issue in validate_record("prediction", record))


def test_manifest_rejects_invalid_or_unordered_host_times():
    record = load("manifest", RUN / "manifest.json")[0]
    record["times"]["host_run_end_s"] = "broken"
    assert any("finite number" in issue for issue in validate_record("manifest", record))
    record["times"]["host_run_end_s"] = record["times"]["host_run_start_s"] - 1
    assert any("out of order" in issue for issue in validate_record("manifest", record))
