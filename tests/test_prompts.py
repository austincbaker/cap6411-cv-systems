"""Gesture prompt, answer schema and answer validation (item 2c). No model needed."""

from __future__ import annotations

import json

import pytest

from contracts import EVENT_LABELS
from vlm.prompts import (
    ANSWER_ERRORS,
    GESTURE_EVENTS,
    GESTURE_PROMPT,
    GESTURE_RESPONSE_FORMAT,
    GESTURE_SCHEMA,
    GESTURES,
    GestureAnswer,
    parse_gesture_answer,
)


def test_vocabulary_is_the_two_selected_gestures_plus_a_negative():
    assert GESTURES == ("thumbs_up", "peace_sign", "none")
    assert set(GESTURE_EVENTS) == {"thumbs_up", "peace_sign"} <= EVENT_LABELS
    assert all(label in GESTURE_PROMPT for label in GESTURES)


def test_schema_allows_exactly_one_field_with_the_vocabulary():
    assert GESTURE_SCHEMA["properties"]["gesture"]["enum"] == list(GESTURES)
    assert GESTURE_SCHEMA["required"] == ["gesture"]
    assert GESTURE_SCHEMA["additionalProperties"] is False
    assert GESTURE_RESPONSE_FORMAT["type"] == "json_schema"
    assert GESTURE_RESPONSE_FORMAT["json_schema"]["schema"] is GESTURE_SCHEMA
    json.dumps(GESTURE_RESPONSE_FORMAT)  # sent as-is in the request body


@pytest.mark.parametrize("gesture", GESTURES)
@pytest.mark.parametrize("layout", ['{{"gesture": "{}"}}', '{{\n  "gesture": "{}"\n}}'])
def test_each_label_and_the_negative_validate(gesture, layout):
    answer = parse_gesture_answer(layout.format(gesture), "stop")
    assert answer == GestureAnswer(gesture) and answer.valid
    assert answer.observation() == {"gesture": gesture}


def test_none_is_a_valid_negative_not_an_unknown():
    negative = parse_gesture_answer('{"gesture": "none"}')
    unknown = parse_gesture_answer("I can't tell.")
    assert negative.valid and negative.gesture == "none" and negative.error is None
    assert not unknown.valid and unknown.gesture is None and unknown.observation() is None


@pytest.mark.parametrize(
    "text,finish_reason,error",
    [
        ("The person is making a thumbs up gesture.", "stop", "not_json"),
        ("thumbs_up", "stop", "not_json"),  # the right word, but not the schema's answer
        ("", "stop", "not_json"),
        (None, None, "not_json"),
        ('{\n  "gesture": "thum', "length", "truncated"),
        ('"thumbs_up"', "stop", "not_object"),
        ('["thumbs_up"]', "stop", "not_object"),
        ("{}", "stop", "missing_gesture"),
        ('{"label": "thumbs_up"}', "stop", "missing_gesture"),
        ('{"gesture": "none", "confidence": 0.9}', "stop", "unexpected_fields"),
        ('{"gesture": "Thumbs_Up"}', "stop", "out_of_vocabulary"),
        ('{"gesture": "thumbs up"}', "stop", "out_of_vocabulary"),
        ('{"gesture": "neither"}', "stop", "out_of_vocabulary"),
        ('{"gesture": null}', "stop", "out_of_vocabulary"),
        ('{"gesture": 1}', "stop", "out_of_vocabulary"),
    ],
)
def test_malformed_partial_and_out_of_vocabulary_answers_are_explicit_failures(
    text, finish_reason, error
):
    answer = parse_gesture_answer(text, finish_reason)
    assert answer == GestureAnswer(None, error) and not answer.valid
    assert error in ANSWER_ERRORS


def test_a_complete_answer_cut_at_the_bound_still_validates():
    # finish_reason only explains a parse failure; a complete answer is judged on its content.
    assert parse_gesture_answer('{"gesture": "peace_sign"}', "length").gesture == "peace_sign"
