import threading
import time

import pytest

from pipeline import QUALITY_LEVELS, Latest, QualityGovernor, Stats, Worker


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def wait_for(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_latest_versions_and_wait():
    latest = Latest()
    assert latest.get() == (0, None)
    latest.set("a")
    assert latest.get() == (1, "a")
    assert latest.wait_newer(0, 0.01) == (1, "a")
    assert latest.wait_newer(1, 0.01) == (1, "a")  # timed out, unchanged

    threading.Timer(0.02, lambda: latest.set("b")).start()
    assert latest.wait_newer(1, 1.0) == (2, "b")


def test_stats_rate_and_ms():
    clock = FakeClock()
    stats = Stats(window_sec=1.0, clock=clock)
    for _ in range(10):
        clock.t += 0.1
        stats.record(0.02)
    assert stats.rate == pytest.approx(10, abs=1)
    assert stats.ms == pytest.approx(20)
    clock.t += 5
    assert stats.rate == 0


def test_worker_skips_to_newest_input():
    source = Latest()
    seen = []
    gate = threading.Event()

    def slow(item):
        gate.wait(1.0)
        seen.append(item)
        return item * 10

    worker = Worker("test", slow, source)
    worker.start()
    try:
        source.set(1)
        assert wait_for(lambda: worker.stats.rate == 0 and source.version == 1)
        time.sleep(0.05)  # worker now busy on item 1
        for item in (2, 3, 4):
            source.set(item)
        gate.set()
        assert wait_for(lambda: worker.output.get()[1] == 40)
        assert seen == [1, 4]  # 2 and 3 arrived while busy and were skipped
        assert worker.stats.ms > 0
    finally:
        worker.stop()


def test_worker_pause_and_resume():
    source = Latest()
    worker = Worker("test", lambda x: x, source, paused=True)
    worker.start()
    try:
        source.set(1)
        time.sleep(0.15)
        assert worker.output.version == 0
        worker.resume()
        source.set(2)
        assert wait_for(lambda: worker.output.get()[1] == 2)
    finally:
        worker.stop()


def test_worker_reports_errors():
    source = Latest()
    worker = Worker("test", lambda x: 1 / 0, source)
    worker.start()
    source.set(1)
    assert wait_for(lambda: worker.error is not None)
    assert isinstance(worker.error, ZeroDivisionError)


def test_worker_max_rate():
    source = Latest()
    worker = Worker("test", lambda x: x, source, max_rate=10)
    worker.start()
    try:
        end = time.monotonic() + 0.5
        i = 0
        while time.monotonic() < end:
            i += 1
            source.set(i)
            time.sleep(0.002)
        assert worker.output.version <= 7  # ~10/s for 0.5 s
    finally:
        worker.stop()


def run_governor(governor, clock, fps, target, seconds, step=0.1):
    drops = 0
    for _ in range(int(seconds / step)):
        clock.t += step
        drops += governor.update(fps, target)
    return drops


def test_governor_steps_down_one_level_at_a_time_and_stops():
    clock = FakeClock()
    gov = QualityGovernor("auto", clock=clock)
    assert run_governor(gov, clock, 30, 30, 20) == 0   # fast enough: never drops
    assert run_governor(gov, clock, 12, 30, 6) == 1    # slow for 5 s: one step
    assert gov.level == 1
    run_governor(gov, clock, 12, 30, 60)
    assert gov.level == len(QUALITY_LEVELS) - 1        # bottoms out
    assert run_governor(gov, clock, 12, 30, 10) == 0
    run_governor(gov, clock, 30, 30, 10)
    assert gov.level == len(QUALITY_LEVELS) - 1        # never steps back up


def test_governor_ignores_short_dips_and_warmup():
    clock = FakeClock()
    gov = QualityGovernor("auto", clock=clock)
    assert run_governor(gov, clock, 5, 30, 2.5) == 0   # warm-up
    for _ in range(5):
        run_governor(gov, clock, 10, 30, 3)
        run_governor(gov, clock, 30, 30, 1)
    assert gov.level == 0


def test_governor_high_and_low_modes():
    clock = FakeClock()
    high = QualityGovernor("high", clock=clock)
    assert run_governor(high, clock, 5, 30, 30) == 0 and high.level == 0
    assert QualityGovernor("low", clock=clock).level == len(QUALITY_LEVELS) - 1
