"""Gesture prompt, answer schema and answer validation (item 2c).

Every request asks one question about one frame, and llama-server constrains the
answer with ``GESTURE_RESPONSE_FORMAT`` (a JSON schema it turns into a grammar), so
a well-behaved server can only return an object such as::

    {"hands": "thumb up", "gesture": "thumbs_up"}
    {"hands": "two fingers raised", "gesture": "peace_sign"}
    {"hands": "none", "gesture": "none"}

``hands`` is the model's own few words about the hands, written before it picks
``gesture``; SmolVLM2 asked for ``gesture`` alone answers ``thumbs_up`` for every
frame. Only ``gesture`` is the observation; ``hands`` stays in the raw text.

``"none"`` is a valid negative: the model saw neither gesture. The application
still validates every answer with :func:`parse_gesture_answer`, because the
constraint can fail (a server that ignores ``response_format``, an answer cut off
at the output bound). An answer that does not validate is *unknown*, never a
negative: its ``gesture`` is ``None`` and ``error`` says why.

The request record keeps its transport ``status`` (``ok`` means the server
answered); the validated ``gesture`` and any ``answer_error`` sit beside it.
These are per-frame observations. Events (a gesture starting or ending) are
derived from them by the application's scene state (item 2b), not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

GESTURES = ("thumbs_up", "peace_sign", "none")
GESTURE_EVENTS = ("thumbs_up", "peace_sign")  # the visible gestures; "none" is neither

GESTURE_PROMPT = (
    "Describe what the person's hands are doing in a few words, then say whether the person "
    "is making a thumbs up, a peace sign, or neither (none)."
)
HANDS_MAX_CHARS = 80  # bounds the description, so the answer fits the output token bound

# Properties in this order: the server's grammar writes ``hands`` before ``gesture``.
GESTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "hands": {"type": "string", "maxLength": HANDS_MAX_CHARS},
        "gesture": {"type": "string", "enum": list(GESTURES)},
    },
    "required": ["hands", "gesture"],
    "additionalProperties": False,
}
ANSWER_FIELDS = frozenset(GESTURE_SCHEMA["properties"])

# OpenAI-style structured output; llama-server compiles the schema to a grammar.
GESTURE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "gesture_observation", "strict": True, "schema": GESTURE_SCHEMA},
}

# Why an answer is not a valid observation.
ANSWER_ERRORS = (
    "truncated",  # the server stopped at the output bound before the answer was complete
    "not_json",  # the text is not JSON
    "not_object",  # JSON, but not an object
    "missing_field",  # no "hands" or no "gesture" field
    "unexpected_fields",  # fields other than "hands" and "gesture"
    "hands_not_text",  # "hands" is not a string
    "out_of_vocabulary",  # "gesture" is not exactly one of GESTURES
)


@dataclass(frozen=True)
class GestureAnswer:
    """One validated answer: ``gesture`` when valid, otherwise ``error``."""

    gesture: Optional[str]
    error: Optional[str] = None

    @property
    def valid(self) -> bool:
        return self.gesture is not None

    def observation(self) -> Optional[dict]:
        """The per-frame observation as logged and passed on, or None when unknown."""
        return None if self.gesture is None else {"gesture": self.gesture}


def parse_gesture_answer(text: Optional[str], finish_reason: Optional[str] = None) -> GestureAnswer:
    """Validate one model answer exactly; nothing is normalized or guessed.

    ``hands`` may say anything (it is never checked against ``gesture``); a
    description longer than ``HANDS_MAX_CHARS`` still validates, since the bound
    is the server's to enforce.

    ``finish_reason`` is the server's; ``"length"`` means the output bound cut
    the answer short, which is reported as ``truncated`` when the text does not
    parse.
    """
    try:
        value = json.loads(text or "")
    except ValueError:
        return GestureAnswer(None, "truncated" if finish_reason == "length" else "not_json")
    if not isinstance(value, dict):
        return GestureAnswer(None, "not_object")
    if not ANSWER_FIELDS <= set(value):
        return GestureAnswer(None, "missing_field")
    if set(value) != ANSWER_FIELDS:
        return GestureAnswer(None, "unexpected_fields")
    if not isinstance(value["hands"], str):
        return GestureAnswer(None, "hands_not_text")
    gesture = value["gesture"]
    if not isinstance(gesture, str) or gesture not in GESTURES:
        return GestureAnswer(None, "out_of_vocabulary")
    return GestureAnswer(gesture)
