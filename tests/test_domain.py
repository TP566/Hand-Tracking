import time

import cv2
import numpy as np
import pytest

from domain import DomainPlayer, DomainState, PrefetchSource, fit_cover, timeline_frame


class StubSource:
    fps = 10.0
    frame_count = 100

    def __init__(self):
        self.reads = []

    def read(self, index):
        self.reads.append(index)
        return np.full((40, 80, 3), index % 256, np.uint8)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_timeline_opening_then_loop():
    assert timeline_frame(0.0, 10, 50, 100) == (DomainState.OPENING, 0)
    assert timeline_frame(4.95, 10, 50, 100) == (DomainState.OPENING, 49)
    assert timeline_frame(5.0, 10, 50, 100) == (DomainState.LOOPING, 50)
    assert timeline_frame(9.95, 10, 50, 100) == (DomainState.LOOPING, 99)
    assert timeline_frame(10.0, 10, 50, 100) == (DomainState.LOOPING, 50)
    assert timeline_frame(23.0, 10, 50, 100) == (DomainState.LOOPING, 80)


def test_player_toggle_cycle():
    clock = FakeClock()
    player = DomainPlayer(StubSource(), loop_start_sec=5, loop_end_sec=None, clock=clock)
    assert player.current_frame(64, 36) is None
    player.toggle()
    assert player.state is DomainState.OPENING
    assert player.current_frame(64, 36).shape == (36, 64, 3)
    clock.t = 12.0
    player.current_frame(64, 36)
    assert player.state is DomainState.LOOPING
    player.toggle()
    assert player.state is DomainState.IDLE
    assert player.current_frame(64, 36) is None


def test_cancel_during_opening_and_restart_from_beginning():
    clock = FakeClock()
    source = StubSource()
    player = DomainPlayer(source, loop_start_sec=5, loop_end_sec=None, clock=clock)
    player.toggle()
    clock.t = 2.0
    player.current_frame(64, 36)
    player.toggle()
    assert not player.active
    player.toggle()
    player.current_frame(64, 36)
    assert source.reads[-1] == 0


def test_same_frame_is_cached():
    clock = FakeClock()
    source = StubSource()
    player = DomainPlayer(source, loop_start_sec=5, loop_end_sec=None, clock=clock)
    player.toggle()
    player.current_frame(64, 36)
    player.current_frame(64, 36)
    assert len(source.reads) == 1


def test_loop_points_clamped_to_video():
    player = DomainPlayer(StubSource(), loop_start_sec=500, loop_end_sec=900)
    assert player.loop_end == 100
    assert player.loop_start == 99


def test_fit_cover_crops_to_target_aspect():
    out = fit_cover(np.zeros((1080, 1920, 3), np.uint8), 640, 480)
    assert out.shape == (480, 640, 3)


def write_test_video(path, frames=30, fps=30):
    """Frames whose brightness encodes their index (index * 8; mp4v shifts colours by a few levels)."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for i in range(frames):
        writer.write(np.full((48, 64, 3), i * 8, np.uint8))
    writer.release()
    return str(path)


def frame_index(frame):
    return round(float(frame.mean()) / 8)


def read_when_ready(source, index, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        frame = source.read(index)
        if frame is not None and frame_index(frame) == index:
            return frame
        time.sleep(0.005)
    return source.read(index)


def test_prefetch_has_first_frames_ready(tmp_path):
    source = PrefetchSource(write_test_video(tmp_path / "v.mp4"))
    try:
        assert source.fps == pytest.approx(30)
        assert frame_index(read_when_ready(source, 0)) == 0
        assert frame_index(read_when_ready(source, 3)) == 3
    finally:
        source.close()


def test_prefetch_read_never_blocks_and_returns_earlier_frame(tmp_path):
    source = PrefetchSource(write_test_video(tmp_path / "v.mp4"))
    try:
        read_when_ready(source, 2)
        start = time.monotonic()
        frame = source.read(25)  # far ahead of what is decoded
        assert time.monotonic() - start < 0.05
        assert frame is None or frame_index(frame) <= 25
        assert frame_index(read_when_ready(source, 25)) == 25
    finally:
        source.close()


def test_prefetch_follows_playback_and_loop_wrap(tmp_path):
    source = PrefetchSource(write_test_video(tmp_path / "v.mp4"))
    try:
        for i in range(5, 30, 3):
            assert frame_index(read_when_ready(source, i)) == i
        assert frame_index(read_when_ready(source, 10)) == 10  # wrapped back to the loop start
        assert source.decoded < 60  # forward playback decodes each frame about once
    finally:
        source.close()


def test_player_starts_and_stops_source(tmp_path):
    source = PrefetchSource(write_test_video(tmp_path / "v.mp4"))
    clock = FakeClock()
    try:
        player = DomainPlayer(source, loop_start_sec=0.5, loop_end_sec=None, clock=clock)
        player.toggle()
        clock.t = 0.8
        player.current_frame(64, 48)
        assert frame_index(read_when_ready(source, 24)) == 24
        player.toggle()  # stop rewinds so the opening is ready next time
        assert wait_for_index(source, 0)
    finally:
        source.close()


def wait_for_index(source, index, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with source._lock:
            if index in source._frames:
                return True
        time.sleep(0.005)
    return False


def make_manager(clock):
    from domain import DomainManager
    return DomainManager({
        "void": DomainPlayer(StubSource(), loop_start_sec=5, loop_end_sec=None, clock=clock),
        "shrine": DomainPlayer(StubSource(), loop_start_sec=2, loop_end_sec=None, clock=clock),
    })


def test_manager_opens_and_closes_same_domain():
    manager = make_manager(FakeClock())
    manager.on_sign("void")
    assert manager.active == "void" and manager.state is DomainState.OPENING
    assert manager.current_frame(64, 36) is not None
    manager.on_sign("void")
    assert manager.active is None and manager.state is DomainState.IDLE
    assert manager.current_frame(64, 36) is None


def test_manager_ignores_other_sign_while_open():
    manager = make_manager(FakeClock())
    manager.on_sign("void")
    manager.on_sign("shrine")
    assert manager.active == "void"
    assert not manager.players["shrine"].active


def test_manager_ignores_unknown_or_disabled_sign():
    manager = make_manager(FakeClock())
    manager.on_sign("missing")
    assert manager.active is None
