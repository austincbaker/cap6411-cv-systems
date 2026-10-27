"""Deterministic checks for the webcam and replay sources (no camera, no model)."""

from __future__ import annotations

import math
import threading
import time

import cv2
import pytest

from src.capture import EndReason, ReplaySource, SourceOpenError, WebcamSource
from tests.fakes.fake_capture import FAIL, CaptureFactory, FakeVideoCapture, solid_frame
from tests.fakes.fake_clock import FakeClock
from tests.fakes.video import write_test_video


@pytest.fixture
def video_path(tmp_path):
    return write_test_video(tmp_path / "clip.avi", frames=20, fps=10.0)


@pytest.fixture
def placeholder_path(tmp_path):
    # ReplaySource checks the path exists before handing it to the (fake) decoder.
    path = tmp_path / "fake.avi"
    path.write_bytes(b"")
    return path


def make_replay(path, capture, clock, drops=None, **kwargs):
    factory = CaptureFactory(lambda: capture)
    on_drop = (lambda *args: drops.append(args)) if drops is not None else None
    return ReplaySource(path, clock=clock, sleep=clock.sleep, capture_factory=factory, on_drop=on_drop, **kwargs)


# --------------------------------------------------------------------------- replay pacing


def test_replay_paces_frames_to_media_time_on_fake_clock(placeholder_path):
    clock = FakeClock(start=500.0)
    capture = FakeVideoCapture([solid_frame(i) for i in range(10)], fps=10.0)
    with make_replay(placeholder_path, capture, clock) as source:
        frames = list(source)

    start = frames[0].host_capture_s
    assert [f.frame_id for f in frames] == list(range(10))
    for frame in frames:
        assert frame.host_capture_s == pytest.approx(start + frame.source_time_s)
        assert frame.host_deadline_s == pytest.approx(frame.host_capture_s)
    # 10 frames at 10 fps represent 1.0 s of observation, including the last frame's period.
    assert clock.now == pytest.approx(start + 1.0)
    assert source.end.reason is EndReason.EOF and source.end.complete is True
    assert source.info.time_method == "media_pos_msec" and not source.info.cfr_assumed
    assert capture.released


def test_replay_frame_ids_increase_and_repeat_across_replays(video_path):
    runs = []
    for _ in range(2):
        clock = FakeClock()
        with ReplaySource(video_path, clock=clock, sleep=clock.sleep) as source:
            runs.append([(f.frame_id, round(f.source_time_s, 6), int(f.image.mean())) for f in source])
        assert source.end.reason is EndReason.EOF and source.end.complete is True
        assert source.info.backend  # whatever OpenCV actually picked is recorded
        assert source.info.observed_width == 64 and source.info.observed_height == 48

    ids = [frame_id for frame_id, _, _ in runs[0]]
    assert ids == sorted(set(ids)) == list(range(20))
    times = [t for _, t, _ in runs[0]]
    assert all(b > a for a, b in zip(times, times[1:]))
    assert runs[0] == runs[1]


def test_real_video_wall_time_matches_clip_length(tmp_path):
    path = write_test_video(tmp_path / "short.avi", frames=8, fps=20.0)  # 0.4 s clip
    started = time.monotonic()
    with ReplaySource(path) as source:
        count = sum(1 for _ in source)
    elapsed = time.monotonic() - started
    assert count == 8
    assert 0.38 <= elapsed < 0.6


@pytest.mark.parametrize("bad_fps", [0.0, -5.0, math.nan, math.inf, 5000.0])
def test_invalid_fps_rejected_when_media_timestamps_unusable(placeholder_path, bad_fps):
    clock = FakeClock()
    capture = FakeVideoCapture([solid_frame(i) for i in range(5)], fps=bad_fps, timestamps_ms=[0.0] * 5)
    source = make_replay(placeholder_path, capture, clock)
    with pytest.raises(SourceOpenError, match="fps"):
        source.open()
    assert capture.released and not source.is_open


def test_constant_frame_rate_fallback_is_recorded(placeholder_path):
    clock = FakeClock()
    capture = FakeVideoCapture([solid_frame(i) for i in range(5)], fps=25.0, timestamps_ms=[0.0] * 5)
    with make_replay(placeholder_path, capture, clock) as source:
        frames = list(source)
    assert source.info.time_method == "frame_index_over_fps"
    assert source.info.cfr_assumed is True
    assert any("constant frame rate" in note for note in source.info.notes)
    assert [f.source_time_s for f in frames] == pytest.approx([i / 25.0 for i in range(5)])


def test_valid_media_timestamps_do_not_need_valid_fps(placeholder_path):
    clock = FakeClock()
    capture = FakeVideoCapture([solid_frame(i) for i in range(4)], fps=0.0, timestamps_ms=[0, 40, 80, 120])
    with make_replay(placeholder_path, capture, clock) as source:
        frames = list(source)
    assert source.info.time_method == "media_pos_msec"
    assert [f.source_time_s for f in frames] == pytest.approx([0.0, 0.04, 0.08, 0.12])


# --------------------------------------------------------------------------- replay outcomes


def test_eof_is_distinct_from_incomplete_source(placeholder_path):
    clock = FakeClock()
    full = FakeVideoCapture([solid_frame(i) for i in range(6)], frame_count=6)
    with make_replay(placeholder_path, full, clock) as source:
        list(source)
    assert source.end.reason is EndReason.EOF and source.end.complete is True
    assert not source.end.reason.is_error

    truncated = FakeVideoCapture([solid_frame(i) for i in range(4)] + [FAIL], frame_count=30)
    with make_replay(placeholder_path, truncated, clock) as source:
        frames = list(source)
    assert len(frames) == 4
    assert source.end.reason is EndReason.INCOMPLETE_SOURCE and source.end.complete is False
    assert source.end.reason.is_error
    assert "4 of 30" in source.end.detail


def test_unknown_frame_count_reports_unverified_coverage(placeholder_path):
    clock = FakeClock()
    capture = FakeVideoCapture([solid_frame(i) for i in range(3)], frame_count=0)
    with make_replay(placeholder_path, capture, clock) as source:
        list(source)
    assert source.end.reason is EndReason.EOF
    assert source.end.complete is None
    assert "unverified" in source.end.detail


def test_empty_frames_are_dropped_with_ids_then_fail_after_limit(placeholder_path):
    clock = FakeClock()
    drops = []
    entries = [solid_frame(0), solid_frame(1), None, solid_frame(3)] + [None] * 5
    capture = FakeVideoCapture(entries)
    with make_replay(placeholder_path, capture, clock, drops=drops, max_consecutive_decode_failures=3) as source:
        frames = list(source)
    assert [f.frame_id for f in frames] == [0, 1, 3]
    assert [(d[0], d[1]) for d in drops] == [(2, "empty_frame"), (4, "empty_frame"), (5, "empty_frame"), (6, "empty_frame")]
    assert source.end.reason is EndReason.DECODE_FAILURES
    assert source.info.drop_counts == {"empty_frame": 4}


def test_missing_and_undecodable_files_fail_to_open(tmp_path):
    with pytest.raises(SourceOpenError, match="not found"):
        ReplaySource(tmp_path / "nope.avi").open()
    garbage = tmp_path / "garbage.avi"
    garbage.write_bytes(b"not a video" * 100)
    source = ReplaySource(garbage)
    with pytest.raises(SourceOpenError):
        source.open()
    assert not source.is_open


def test_video_with_no_decodable_frames_fails_to_open(placeholder_path):
    capture = FakeVideoCapture([None, None])
    source = make_replay(placeholder_path, capture, FakeClock())
    with pytest.raises(SourceOpenError, match="no decodable frames"):
        source.open()
    assert capture.released


# --------------------------------------------------------------------------- lifecycle


def test_interrupt_releases_capture_and_source_reopens(video_path):
    clock = FakeClock()
    source = ReplaySource(video_path, clock=clock, sleep=clock.sleep)
    with pytest.raises(KeyboardInterrupt):
        with source:
            for frame in source:
                if frame.frame_id == 3:
                    raise KeyboardInterrupt
    assert source.end.reason is EndReason.INTERRUPTED
    assert not source.is_open

    with source:
        first = source.read()
    assert first.frame_id == 0
    assert source.end.reason is EndReason.STOPPED  # closed early by the consumer, not EOF
    assert not source.is_open


def test_consumer_exception_is_recorded_and_capture_released(placeholder_path):
    capture = FakeVideoCapture([solid_frame(i) for i in range(5)])
    source = make_replay(placeholder_path, capture, FakeClock())
    with pytest.raises(ValueError):
        with source:
            next(iter(source))
            raise ValueError("downstream broke")
    assert source.end.reason is EndReason.CONSUMER_ERROR
    assert "downstream broke" in source.end.detail
    assert capture.released


def test_stop_from_another_thread_wakes_a_sleeping_replay(tmp_path):
    path = write_test_video(tmp_path / "slow.avi", frames=4, fps=1.0)  # 1 s between frames
    source = ReplaySource(path)
    with source:
        assert source.read().frame_id == 0
        timer = threading.Timer(0.1, source.stop)
        timer.start()
        started = time.monotonic()
        assert source.read() is None
        elapsed = time.monotonic() - started
        timer.join()
    assert source.end.reason is EndReason.STOPPED
    assert elapsed < 0.5
    assert not timer.is_alive()


def test_slow_consumer_neither_slows_nor_speeds_up_replay(placeholder_path):
    clock = FakeClock(start=0.0)
    drops = []
    capture = FakeVideoCapture([solid_frame(i) for i in range(50)], fps=10.0)  # 5 s clip
    with make_replay(placeholder_path, capture, clock, drops=drops) as source:
        delivered = []
        for frame in source:
            delivered.append(frame)
            clock.sleep(0.35)  # consumer takes 3.5 frame periods per frame

    start = delivered[0].host_capture_s
    # Real time is preserved: the run lasts the clip length (plus at most the consumer's last stall),
    # not 50 * 0.35 = 17.5 s (paused) and not 0 s (decode speed).
    assert 5.0 <= clock.now - start <= 5.0 + 0.35
    for frame in delivered:
        # Never early, and never later than one frame period behind the source timeline.
        assert frame.host_capture_s >= start + frame.source_time_s - 1e-9
        assert frame.host_capture_s - (start + frame.source_time_s) <= 0.1 + 1e-9
    assert {reason for _, reason, _, _ in drops} == {"replay_late"}
    assert len(delivered) + len(drops) == 50
    ids = [f.frame_id for f in delivered] + [d[0] for d in drops]
    assert sorted(ids) == list(range(50))
    # Late frames are skipped without paying the decode cost.
    assert capture.retrieves < capture.grabs


# --------------------------------------------------------------------------- webcam


def make_webcam(capture, clock=None, drops=None, **kwargs):
    factory = CaptureFactory(lambda: capture)
    on_drop = (lambda *args: drops.append(args)) if drops is not None else None
    source = WebcamSource(0, clock=clock or FakeClock(), capture_factory=factory, on_drop=on_drop, **kwargs)
    return source, factory


def test_webcam_open_failure_is_explicit():
    capture = FakeVideoCapture([], opened=False)
    source, _ = make_webcam(capture)
    with pytest.raises(SourceOpenError, match="could not open camera"):
        source.open()
    assert capture.released and not source.is_open


def test_webcam_opened_but_no_frame_is_an_open_failure():
    capture = FakeVideoCapture([FAIL])
    source, _ = make_webcam(capture)
    with pytest.raises(SourceOpenError, match="no frame"):
        source.open()
    assert capture.released


def test_webcam_records_observed_settings_not_requested_ones():
    capture = FakeVideoCapture([solid_frame(i) for i in range(3)], fps=0.0, width=640, height=480, backend="AVFOUNDATION")
    source, factory = make_webcam(capture, width=1920, height=1080, fps=60)
    with source:
        frame = source.read()
    info = source.info
    assert info.backend == "AVFOUNDATION"
    assert (info.requested_width, info.requested_height, info.requested_fps) == (1920, 1080, 60)
    assert (info.observed_width, info.observed_height) == (640, 480)
    assert (frame.width, frame.height) == (640, 480)
    assert info.observed_fps is None  # backend reported 0 fps: recorded as unknown, not 0
    assert info.buffer_size_accepted is False
    assert any("requested width 1920" in note for note in info.notes)
    assert factory.calls == [(0, cv2.CAP_ANY)]


def test_webcam_frames_have_ids_and_host_time_but_no_media_time():
    clock = FakeClock(start=10.0)
    capture = FakeVideoCapture([solid_frame(i) for i in range(3)])
    source, _ = make_webcam(capture, clock=clock)
    with source:
        frames = []
        for frame in source:
            frames.append(frame)
            clock.advance(0.033)
            if len(frames) == 3:
                break
    assert [f.frame_id for f in frames] == [0, 1, 2]
    assert all(f.source_time_s is None for f in frames)
    assert [f.host_capture_s for f in frames] == pytest.approx([10.0, 10.033, 10.066])
    assert source.info.time_method == "none_host_capture_only"


def test_webcam_transient_failure_is_a_drop_and_disconnect_is_not_eof():
    drops = []
    entries = [solid_frame(0), FAIL, solid_frame(2)] + [FAIL] * 3
    capture = FakeVideoCapture(entries)
    source, _ = make_webcam(capture, drops=drops, max_consecutive_failures=3)
    with source:
        frames = list(source)
    assert [f.frame_id for f in frames] == [0, 2]
    assert [(d[0], d[1]) for d in drops] == [(1, "read_failed"), (3, "read_failed"), (4, "read_failed"), (5, "read_failed")]
    assert source.end.reason is EndReason.DISCONNECTED
    assert source.end.reason is not EndReason.EOF and source.end.reason.is_error
    assert capture.released


def test_webcam_capture_closing_reports_disconnect():
    capture = FakeVideoCapture([solid_frame(i) for i in range(10)], close_after=3)
    source, _ = make_webcam(capture)
    with source:
        frames = list(source)
    assert len(frames) == 3
    assert source.end.reason is EndReason.DISCONNECTED


def test_webcam_releases_and_reopens():
    source, factory = make_webcam(None)
    factory._make = lambda: FakeVideoCapture([solid_frame(i) for i in range(5)])
    for _ in range(2):
        with source:
            assert source.read().frame_id == 0
        assert not source.is_open
    assert len(factory.created) == 2
    assert all(c.released for c in factory.created)


@pytest.mark.parametrize("device", [-1, "", "  ", True, 1.5])
def test_webcam_rejects_invalid_device_ids(device):
    with pytest.raises(SourceOpenError):
        WebcamSource(device)


def test_webcam_accepts_index_strings_and_paths():
    assert WebcamSource("2").device == 2
    assert WebcamSource("/dev/video0").device == "/dev/video0"
