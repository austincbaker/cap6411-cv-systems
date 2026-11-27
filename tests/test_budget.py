"""Energy-budget controller (item 3a) and the app's --policy budget (item 3c). No model needed."""

from __future__ import annotations

import copy
import csv
import json
import random
from pathlib import Path

import pytest

from app.main import main, parse_args
from budget import BudgetConfig, BudgetController, CostEntry, CostTable, load_cost_table
from contracts import read_artifact, validate_record
from scripts import analyze_energy_suite as analyze
from scripts import energy_suite as suite
from tests import test_energy_suite as suite_tests
from tests.fakes.fake_llama import FakeLlama
from tests.test_app_baseline import config_for, read_jsonl, run_baseline
from tests.test_gate import write_event_clip

ROOT = Path(__file__).resolve().parents[1]
TABLE = CostTable(
    entries=(
        CostEntry(None, 6.0, 0.6),
        CostEntry(768, 4.8, 0.48),
        CostEntry(384, 3.0, 0.3),
    ),
    placeholder=False,
)


def controller(budget_w=1.0, **kwargs) -> BudgetController:
    c = BudgetController(BudgetConfig(budget_wh_per_hour=budget_w, **kwargs), TABLE)
    c.start(0.0)
    return c


# ---------------------------------------------------------------------------- bucket


def test_bucket_starts_full_refills_at_the_budget_rate_and_caps():
    c = controller(budget_w=2.0)  # 2 Wh/h = 2 J/s; capacity 2 full calls = 12 J
    assert c.capacity_j == 12.0 and c.level_j == 12.0
    v = c.step(0.0, "a")
    assert v.decision == "admit_full" and v.est_cost_j == 6.0 and c.level_j == 6.0
    c.step(1.5)  # +3 J
    assert c.level_j == pytest.approx(9.0)
    c.step(100.0)  # capped
    assert c.level_j == 12.0
    assert c.allowance_j(100.0) == pytest.approx(12.0 + 200.0)


def test_admits_full_then_reduced_then_defers_by_what_the_bucket_holds():
    c = controller(budget_w=0.1, capacity_j=13.0)
    assert c.step(0.0, "a").decision == "admit_full"  # 13 -> 7
    v = c.step(0.0, "b")  # 7 J: full (6) still fits
    assert v.decision == "admit_full" and c.level_j == pytest.approx(1.0)
    c.level_j = 5.0
    v = c.step(0.0, "c")
    assert (v.decision, v.image_max_side, v.est_cost_j) == ("admit_reduced", 768, 4.8)
    c.level_j = 3.5
    v = c.step(0.0, "d")
    assert (v.decision, v.image_max_side) == ("admit_reduced", 384)
    c.level_j = 1.0
    v = c.step(0.0, "e")
    assert v.decision == "defer" and v.item is None and c.pending == "e"
    assert v.bucket_after_j == v.bucket_before_j == 1.0


def test_a_deferred_change_is_sent_as_soon_as_the_bucket_refills():
    c = controller(budget_w=1.0, capacity_j=6.0)
    assert c.step(0.0, "first").decision == "admit_full"  # bucket 0
    assert c.step(0.5, "change").decision == "defer"
    assert c.step(1.0).decision == "defer"  # gate quiet, change still pending
    assert c.step(2.5).decision == "defer"  # 2.5 J < 3.0 J cheapest
    v = c.step(3.0)  # 3.0 J: the cheapest size fits
    assert v.decision == "admit_reduced" and v.item == "change" and v.image_max_side == 384
    assert c.pending is None
    assert c.step(3.5).decision == "no_change"


def test_a_newer_trigger_replaces_the_pending_change():
    c = controller(budget_w=1.0, capacity_j=6.0)
    c.step(0.0, "first")
    c.step(0.5, "old")
    v = c.step(1.0, "new")
    assert v.decision == "defer" and v.replaced_pending and c.pending == "new"
    assert c.step(3.5).item == "new"  # 3.5 J at t=3.5


def test_a_stale_pending_change_is_dropped_not_sent_late():
    c = controller(budget_w=0.01, capacity_j=6.0, pending_max_age_s=10.0)
    c.step(0.0, "first")
    c.step(1.0, "change")
    assert c.step(11.0).decision == "defer"  # exactly 10 s old: still kept
    v = c.step(11.5)
    assert v.decision == "drop" and v.item == "change" and c.pending is None
    assert c.counts["drop"] == 1


def test_busy_ticks_keep_the_pending_change_and_refill():
    c = controller(budget_w=1.0, capacity_j=6.0)
    c.step(0.0, "first")
    v = c.step(0.5, "change", busy=True)
    assert v.decision == "busy" and c.pending == "change"
    assert c.step(1.0, busy=True).decision == "busy"
    assert c.step(3.0).item == "change"
    assert c.step(3.5, busy=True).decision == "busy"


def test_settlement_rescales_by_measured_latency_and_can_go_negative():
    c = controller(budget_w=1.0, capacity_j=6.0)
    v = c.step(0.0, "a")
    s = c.settle(0.0, None, v.est_cost_j, 1.2)  # twice the calibrated 0.6 s
    assert s.decision == "settle" and s.est_cost_j == pytest.approx(12.0)
    assert c.level_j == pytest.approx(-6.0) and c.spent_j == pytest.approx(12.0)
    assert c.step(8.0, "b").decision == "defer"  # -6 + 8 = 2 J
    assert c.step(9.0).decision == "admit_reduced"  # 3 J


def test_settlement_off_keeps_the_estimate():
    c = controller(budget_w=1.0, settle=False)
    v = c.step(0.0, "a")
    assert c.settle(0.0, None, v.est_cost_j, 5.0).est_cost_j == 6.0
    assert c.spent_j == 6.0


def test_estimated_spend_never_exceeds_capacity_plus_budget_times_time():
    rng = random.Random(7)
    for budget_w in (0.05, 0.5, 3.0):
        c = controller(budget_w=budget_w, settle=False)
        t = 0.0
        for _ in range(2000):
            t += 0.5
            c.step(t, "x" if rng.random() < 0.4 else None, busy=rng.random() < 0.2)
            assert c.spent_j <= c.capacity_j + budget_w * t + 1e-9
        assert c.counts["admit_full"] + c.counts["admit_reduced"] > 0


def test_reduced_options_are_smaller_and_cheaper_than_the_run_size():
    assert [o.image_max_side for o in TABLE.options(None)] == [None, 768, 384]
    assert [o.image_max_side for o in TABLE.options(768)] == [768, 384]
    assert [o.image_max_side for o in TABLE.options(384)] == [384]
    with pytest.raises(ValueError, match="no entry"):
        TABLE.options(512)


def test_cost_table_loads_and_rejects_bad_tables(tmp_path):
    table = load_cost_table(ROOT / "configs/budget_costs.json")
    assert table.placeholder is True and table.entry(None) is not None
    assert [o.image_max_side for o in table.options(None)] == [None, 768, 384]
    bad = tmp_path / "bad.json"
    for data in (
        {"table_version": 2, "entries": []},
        {"table_version": 1, "entries": [{"image_max_side": None, "j_per_call": 0}]},
        {
            "table_version": 1,
            "entries": [
                {"image_max_side": 384, "j_per_call": 1},
                {"image_max_side": 384, "j_per_call": 2},
            ],
        },
    ):
        bad.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            load_cost_table(bad)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"budget_wh_per_hour": 0},
        {"budget_wh_per_hour": 1, "capacity_j": 0},
        {"budget_wh_per_hour": 1, "pending_max_age_s": 0},
    ],
)
def test_invalid_budget_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        BudgetConfig(**kwargs)


# ---------------------------------------------------------------------------- app


def tiny_table(tmp_path) -> Path:
    path = tmp_path / "costs.json"
    path.write_text(
        json.dumps(
            {
                "table_version": 1,
                "placeholder": False,
                "source": "test",
                "entries": [
                    {"image_max_side": None, "j_per_call": 1.0, "latency_s": 0.01},
                    {"image_max_side": 64, "j_per_call": 0.5, "latency_s": 0.01},
                ],
            }
        )
    )
    return path


def budget_run(tmp_path, clip, budget, *extra, name="budget"):
    config = config_for(
        tmp_path,
        "--interval-s",
        "0.25",
        "--policy",
        "budget",
        "--budget-wh-per-hour",
        str(budget),
        "--budget-costs",
        str(tiny_table(tmp_path)),
        "--budget-no-settle",
        *extra,
        video=clip,
        name=name,
    )
    return run_baseline(config, FakeLlama())


def test_a_generous_budget_sends_what_the_gate_sends(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi")
    _, result = budget_run(tmp_path, clip, 1000.0)
    assert result.exit_code == 0 and result.manifest["policy"] == "budget"
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert [r["gate_reason"] for r in requests] == ["gate_initial", "gate_change"]
    assert [r["budget_decision"] for r in requests] == ["admit_full", "admit_full"]
    assert all(r["budget_cost_j"] == 1.0 for r in requests)
    summary = result.manifest["budget"]
    assert summary["decisions"]["admit_full"] == 2 and summary["decisions"]["defer"] == 0
    assert summary["cost_table"]["source"] == "test"
    assert result.manifest["files"]["budget"] == "budget.jsonl"


def test_a_tight_budget_defers_then_sends_the_change_reduced(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=4.0)
    # capacity 1 J (one full call), refill 0.2 J/s: after the first call the change at ~2 s
    # waits until the bucket holds 0.5 J (the 64 px size), about 2.5 s after the first call.
    _, result = budget_run(tmp_path, clip, 0.2, "--budget-capacity-j", "1")
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    drops = read_jsonl(result.run_dir / "drops.jsonl")
    lines = read_jsonl(result.run_dir / "budget.jsonl")
    assert [r["budget_decision"] for r in requests] == ["admit_full", "admit_reduced"]
    assert requests[1]["budget_image_max_side"] == 64
    deferred = [d for d in drops if d["reason"] == "budget_deferred"]
    assert deferred and all(d["origin"] == "budget" for d in deferred)
    assert requests[1]["source_time_s"] >= 1.0  # the change, not the empty desk
    assert 2.2 <= requests[1]["host_tick_s"] - requests[0]["host_tick_s"] <= 2.8

    # One budget line per tick plus one per settled call; every tick accounted once.
    ticks = [b for b in lines if b["decision"] != "settle"]
    assert [b["tick_index"] for b in ticks] == list(range(len(ticks)))
    assert sum(b["decision"] == "settle" for b in lines) == len(requests)
    accounted = sorted(
        [r["tick_index"] for r in requests]
        + [d["tick_index"] for d in drops if d["origin"] != "source"]
    )
    assert accounted == list(range(len(accounted)))
    assert all(b["spent_j"] <= b["allowance_j"] + 1e-9 for b in lines)
    assert all(validate_record("budget", b) == [] for b in lines)


def test_budget_policy_needs_a_budget_and_a_valid_table(tmp_path, capsys):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=0.5)
    with pytest.raises(SystemExit):
        parse_args(["--source", "replay", "--video", str(clip), "--policy", "budget"])
    with pytest.raises(SystemExit):
        parse_args(["--source", "replay", "--video", str(clip), "--budget-wh-per-hour", "1"])
    missing = tmp_path / "nope.json"
    code = main(
        [
            "--source",
            "replay",
            "--video",
            str(clip),
            "--policy",
            "budget",
            "--budget-wh-per-hour",
            "1",
            "--budget-costs",
            str(missing),
            "--profile",
            str(tmp_path / "no-profile.json"),
        ]
    )
    assert code == 2


def test_contract_fixtures_accept_good_budget_lines_and_reject_bad_ones():
    fixtures = ROOT / "tests/fixtures/contracts"
    records, issues = read_artifact("budget", fixtures / "budget_valid.jsonl")
    assert issues == [] and [r["decision"] for r in records][:2] == ["admit_full", "settle"]
    # The deferred change at frame 45 is the one sent reduced two ticks later.
    assert records[-1]["sent_frame_id"] == records[-2]["pending_frame_id"] == 45
    records, issues = read_artifact("budget", fixtures / "invalid" / "budget_bad.jsonl")
    lines = {int(i.location.rsplit(":", 1)[-1]) for i in issues}
    assert lines == {1, 2, 3, 4, 5, 6}, [str(i) for i in issues]
    text = " ".join(i.message for i in issues)
    for expected in ("defer must not change", "needs est_cost_j and sent_frame_id", "spend",
                     "above capacity", "settle needs", "needs tick_index"):  # fmt: skip
        assert expected in text


# ---------------------------------------------------------------------------- energy suite


def budget_config(**block):
    config = copy.deepcopy(suite_tests.CONFIG)
    config["blocks"]["budget"].update({"enabled": True, **block})
    return config


def test_budget_block_adds_a_calibration_run_and_one_run_per_budget():
    runs = suite.expand(budget_config())
    budget = [r for r in runs if r["block"] == "budget"]
    assert [r["name"] for r in budget] == [
        "budget_calib_px384_1",
        "budget_f0.5_1",
        "budget_f0.25_1",
        "budget_f0.1_1",
    ]
    calib = budget[0]["condition"]
    assert calib["policy"] == "fixed_interval" and calib["app_args"] == {"image_max_side": 384}
    assert all(r["condition"]["interval_s"] == 0.5 for r in budget[1:])
    plan = suite.estimate(budget, 585.0, 90.0)
    assert suite.hms(plan["total_s"]) == "46 min"

    # The image block already measures 384 px at the default output bound: no extra run.
    config = budget_config(budget_wh_per_hour=[1.5])
    config["blocks"]["image"]["enabled"] = True
    names = [r["name"] for r in suite.expand(config) if r["block"] == "budget"]
    assert names[0] == "budget_f0.5_1" and names[-1] == "budget_wh1.5_1"


def write_calibration_suite(tmp_path) -> Path:
    suite_dir = suite_tests.write_suite(tmp_path)  # idle 5.5 W, fixed 2 s 9.5 W battery, 290 calls
    image = {
        "name": "budget_calib_px384",
        "policy": "fixed_interval",
        "interval_s": 2.0,
        "app_args": {"image_max_side": 384},
    }
    record = suite_tests.fake_record(
        "budget_calib_px384", image, 1, package_w=2.0, system_w=7.0, battery_w=7.5, calls=290,
        named=1,
    )  # fmt: skip
    record["block"] = "budget"
    record["calls"]["latency_median_s"] = 0.3
    (suite_dir / record["name"]).mkdir()
    (suite_dir / record["name"] / "suite_run.json").write_text(json.dumps(record))
    return suite_dir


def test_calibration_derives_joules_per_call_above_idle_per_image_size(tmp_path):
    suite_dir = write_calibration_suite(tmp_path)
    table = analyze.calibrate(analyze.load_runs(suite_dir), "suite-test")
    assert table["placeholder"] is False and table["domain"] == analyze.DOMAIN_LABEL["battery"]
    full, small = table["entries"]
    assert full["image_max_side"] is None and small["image_max_side"] == 384
    assert full["j_per_call"] == pytest.approx(4.0 * 600 / 290)  # (9.5 - 5.5) W x 600 s / calls
    assert small["j_per_call"] == pytest.approx(2.0 * 600 / 290)
    assert full["latency_s"] == 0.5 and small["latency_s"] == 0.3
    assert len(full["runs"]) == 2
    # The controller reads what calibration writes.
    assert suite.main(["calibrate", str(suite_dir)]) == 0
    loaded = load_cost_table(suite_dir / "budget_costs.json")
    assert [o.image_max_side for o in loaded.options(None)] == [None, 384]


def test_calibration_needs_idle_and_full_size_runs(tmp_path):
    with pytest.raises(ValueError, match="idle"):
        analyze.calibrate([])
    assert suite.main(["calibrate", str(tmp_path)]) == 2


def test_budget_runs_resolve_their_budget_from_the_fresh_calibration(tmp_path):
    suite_dir = write_calibration_suite(tmp_path)
    config = budget_config()
    run = next(r for r in suite.expand(config) if r["name"] == "budget_f0.25_1")
    resolved, info = suite.resolve_budget(run, suite_dir, config)
    reference = (4.0 * 600 / 290) / 2.0  # full-size J per call over the 2 s reference interval
    assert info["reference_fixed_wh_per_hour"] == pytest.approx(reference)
    assert info["wh_per_hour"] == pytest.approx(0.25 * reference)
    assert info["costs_placeholder"] is False and info["calibration_error"] is None
    command = suite.app_command(resolved, Path("clip.mov"), Path("p.json"), tmp_path / "app", None)
    assert command[command.index("--policy") + 1] == "budget"
    assert float(command[command.index("--budget-wh-per-hour") + 1]) == pytest.approx(
        0.25 * reference, rel=1e-4
    )
    assert command[command.index("--budget-costs") + 1] == str(suite_dir / "budget_costs.json")

    # Nothing to calibrate from yet: the placeholder table, said so in the record.
    empty = tmp_path / "empty"
    empty.mkdir()
    _, info = suite.resolve_budget(run, empty, config)
    assert info["costs_placeholder"] is True and "idle" in info["calibration_error"]


def test_analysis_reports_measured_energy_against_each_budget(tmp_path):
    suite_dir = write_calibration_suite(tmp_path)
    for fraction, battery_w, named in ((0.5, 7.0, 2), (0.1, 5.9, 1)):
        condition = {
            "name": f"budget_f{fraction:g}",
            "policy": "budget",
            "interval_s": 0.5,
            "budget": {"fraction_of_fixed": fraction},
            "app_args": {"budget_wh_per_hour": fraction * 4.0},
        }
        record = suite_tests.fake_record(
            condition["name"], condition, 1, package_w=1.2, system_w=battery_w - 0.5,
            battery_w=battery_w, calls=40, named=named,
        )  # fmt: skip
        record["block"] = "budget"
        record["budget"] = {
            "wh_per_hour": fraction * 4.0,
            "fraction_of_fixed": fraction,
            "costs_placeholder": False,
        }
        record["budget_summary"] = {
            "estimated_spend_wh_per_hour": fraction * 3.8,
            "decisions": {"admit_full": 30, "admit_reduced": 10, "defer": 50, "drop": 2},
        }
        run_dir = suite_dir / record["name"]
        (run_dir / "app").mkdir(parents=True)
        (run_dir / "suite_run.json").write_text(json.dumps(record))
        (run_dir / "app" / "budget.jsonl").write_text(
            "\n".join(
                json.dumps({"host_tick_s": 10.0 + t, "spent_j": 1.5 * t, "allowance_j": 12 + 2 * t})
                for t in range(0, 600, 5)
            )
        )
    assert analyze.main([str(suite_dir), "--out", str(tmp_path / "out")]) == 0
    rows = {r["run"]: r for r in csv.DictReader((tmp_path / "out/budget.csv").open())}
    assert set(rows) == {"budget_f0.5_1", "budget_f0.1_1"}
    half = rows["budget_f0.5_1"]
    assert float(half["budget_wh_per_hour"]) == 2.0
    assert float(half["incremental_w"]) == pytest.approx(1.5)  # 7.0 - 5.5 idle
    assert float(half["measured_over_budget"]) == pytest.approx(0.75)
    assert half["admit_reduced"] == "10" and half["drop"] == "2" and half["windows_named"] == "2"
    for name in ("budget.png", "budget_spend.png"):
        assert (tmp_path / "out" / name).stat().st_size > 1000
