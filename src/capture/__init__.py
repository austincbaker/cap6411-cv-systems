"""Webcam and real-time replay frame sources (item 1c).

Typical use::

    from src.capture import ReplaySource, SourceOpenError

    with ReplaySource("clip.mp4") as source:
        for frame in source:
            ...  # frame.frame_id, frame.source_time_s, frame.host_capture_s, frame.image (BGR)
    print(source.end.reason, source.info.as_dict())
"""

from .frame import (
    EndReason,
    Frame,
    SourceBase,
    SourceEnd,
    SourceInfo,
    SourceOpenError,
)
from .replay import ReplaySource
from .webcam import WebcamSource

__all__ = [
    "EndReason",
    "Frame",
    "ReplaySource",
    "SourceBase",
    "SourceEnd",
    "SourceInfo",
    "SourceOpenError",
    "WebcamSource",
]
