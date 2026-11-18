"""Gesture prompt, answer schema and answer validation (item 2c).

Every request asks one question about one frame, and llama-server constrains the
answer with ``GESTURE_RESPONSE_FORMAT`` (a JSON schema it turns into a grammar), so
a well-behaved server can only return one of::

    {"gesture": "thumbs_up"}    {"gesture": "peace_sign"}    {"gesture": "none"}

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
    "Is the person making a thumbs up, a peace sign, or neither? "
    "Answer with one word: thumbs_up, peace_sign, or none."
)

GESTURE_SCHEMA = {
    "type": "object",
    "properties": {"gesture": {"type": "string", "enum": list(GESTURES)}},
    "required": ["gesture"],
    "additionalProperties": False,
}

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
    "missing_gesture",  # no "gesture" field
    "unexpected_fields",  # fields other than "gesture"
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
    if "gesture" not in value:
        return GestureAnswer(None, "missing_gesture")
    if set(value) != {"gesture"}:
        return GestureAnswer(None, "unexpected_fields")
    gesture = value["gesture"]
    if not isinstance(gesture, str) or gesture not in GESTURES:
        return GestureAnswer(None, "out_of_vocabulary")
    return GestureAnswer(gesture)
