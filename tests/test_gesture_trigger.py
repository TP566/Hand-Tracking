from gesture_trigger import HoldTrigger


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def feed(trigger, clock, values, dt=1 / 30):
    fired = []
    for v in values:
        fired.append(trigger.update(v))
        clock.t += dt
    return fired


def test_fires_once_after_hold():
    clock = FakeClock()
    trig = HoldTrigger(hold_frames=5, cooldown_sec=1.0, clock=clock)
    fired = feed(trig, clock, [True] * 20)
    assert fired.count(True) == 1
    assert fired.index(True) == 4


def test_short_flicker_does_not_fire():
    clock = FakeClock()
    trig = HoldTrigger(hold_frames=5, cooldown_sec=1.0, clock=clock)
    assert not any(feed(trig, clock, [True, True, True, False, True, True, True, False]))


def test_needs_release_and_cooldown_before_refiring():
    clock = FakeClock()
    trig = HoldTrigger(hold_frames=3, cooldown_sec=1.0, clock=clock)
    assert feed(trig, clock, [True] * 3)[-1]
    # Released and re-held within the cooldown: ignored.
    assert not any(feed(trig, clock, [False] + [True] * 5))
    # Released after the cooldown, then held again: fires.
    clock.t += 1.0
    assert feed(trig, clock, [False] + [True] * 3)[-1]


def test_progress_reports_hold_fraction():
    clock = FakeClock()
    trig = HoldTrigger(hold_frames=4, cooldown_sec=1.0, clock=clock)
    feed(trig, clock, [True, True])
    assert trig.progress == 0.5
