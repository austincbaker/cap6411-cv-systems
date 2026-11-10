"""Scene state and shared event derivation (item 2b). No camera or model needed."""

from __future__ import annotations

from app.state import SceneObservation, SceneState, derive_events, parse_observation
from contracts import EVENT_LABELS
from tests.fakes.fake_llama import FakeLlama
from tests.test_app_baseline import config_for, read_jsonl, run_baseline
from tests.test_gate import write_event_clip


def obs(*objects, person=False):
    return SceneObservation(person=person, objects=frozenset(objects))


def test_parse_reads_smolvlm_style_lists_down_to_head_nouns():
    assert parse_observation("The objects are a gray mug and a red phone.") == obs("mug", "phone")
    assert parse_observation("In the image, there is a laptop, a coffee mug, and a woman.") == obs(
        "laptop", "mug", person=True
    )
    assert parse_observation("none") == obs()


def test_parse_rejects_text_with_nothing_usable():
    assert parse_observation("") is None
    assert parse_observation("  ...  ") is None
    assert parse_observation(None) is None


def test_derive_emits_contract_labels_for_each_change():
    events = derive_events(obs("mug", "laptop"), obs("laptop", "phone", person=True))
    assert events == [
        ("person_enters", None),
        ("object_placed", "phone"),
        ("object_removed", "mug"),
    ]
    assert {label for label, _ in events} <= EVENT_LABELS
    assert derive_events(obs("mug", person=True), obs()) == [
        ("person_leaves", None),
        ("object_removed", "mug"),
    ]


def test_first_observation_sets_the_scene_and_repeats_emit_nothing():
    scene = SceneState()
    assert scene.update("a mug, a laptop") == []
    assert scene.update("The objects are a laptop and a mug.") == []  # same scene, reworded
    assert scene.update("a laptop") == [("object_removed", "mug")]


def test_invalid_text_leaves_the_confirmed_scene_intact():
    scene = SceneState()
    scene.update("a mug")
    assert scene.update("") is None
    assert scene.confirmed == obs("mug")
    assert scene.update("a mug") == []


def test_app_writes_predictions_through_the_shared_derivation(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=1.5)
    texts = ["a laptop", "a laptop, a mug", "...", "a laptop, a mug, a man"]
    llama = FakeLlama(texts=texts)
    _, result = run_baseline(config_for(tmp_path, "--interval-s", "0.25", video=clip), llama)
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    predictions = read_jsonl(result.run_dir / "predictions.jsonl")
    by_request = {r["request_id"]: r for r in requests}

    assert [(p["label"], p["object"]) for p in predictions] == [
        ("object_placed", "mug"),
        ("person_enters", None),
    ]
    for p in predictions:
        r = by_request[p["request_id"]]
        assert p["frame_id"] == r["frame_id"] and p["source_time_s"] == r["source_time_s"]
        assert p["available_source_time_s"] >= p["source_time_s"]
    counts = result.manifest["counts"]
    assert counts["observation_invalid"] == 1  # "..." is ok but lists nothing: scene kept
    assert counts["prediction:object_placed"] == 1
    assert result.manifest["files"]["prediction"] == "predictions.jsonl"
    assert llama.completions[0]["messages"][0]["content"][0]["text"].startswith("Name the objects")


def test_gated_and_fixed_runs_share_the_derivation(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=3.0)
    llama = FakeLlama(texts=["a laptop", "a laptop, a mug"])
    _, result = run_baseline(
        config_for(
            tmp_path,
            "--interval-s",
            "0.25",
            "--policy",
            "gated",
            *(
                "--gate-threshold",
                "0.05",
                "--gate-persist-checks",
                "1",
                "--gate-min-interval-s",
                "0",
            ),
            video=clip,
        ),
        llama,
    )
    predictions = read_jsonl(result.run_dir / "predictions.jsonl")
    assert [(p["label"], p["object"]) for p in predictions] == [("object_placed", "mug")]
    assert 0.9 <= predictions[0]["source_time_s"] <= 1.5
