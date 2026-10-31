import numpy as np

from domain import DomainPlayer, DomainState, fit_cover, timeline_frame


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
