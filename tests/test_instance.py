from instance import app_running, hold_app_lock


def test_lock_reports_running_until_released(tmp_path):
    p = tmp_path / ".app.lock"
    assert not app_running(p)
    lock = hold_app_lock(p)
    assert app_running(p)
    lock.release()
    assert not app_running(p)


def test_release_is_idempotent(tmp_path):
    p = tmp_path / ".app.lock"
    lock = hold_app_lock(p)
    lock.release()
    lock.release()
    assert not app_running(p)
