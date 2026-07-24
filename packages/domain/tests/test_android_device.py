"""VF-506 Android 真机 domain 测试：§7.2 就绪门（前台账号红线）+ 单设备单 Job。"""

from videoforge_domain import (
    DeviceCheck,
    DeviceReadinessCriteria,
    DeviceState,
    can_dispatch_to_device,
    check_device_readiness,
    is_device_ready,
)


def _state(**over) -> DeviceState:
    base = dict(
        device_id="d1", battery_pct=80, storage_free_mb=2000, network_online=True,
        unlocked=True, app_version="30.1", foreground_account_id="acct_9",
    )
    base.update(over)
    return DeviceState(**base)


def _readiness(state, **kw):
    return check_device_readiness(
        state, expected_account_id=kw.pop("expected_account_id", "acct_9"), **kw)


# --- §7.2 就绪门 ----------------------------------------------------------

def test_all_good_is_ready():
    r = _readiness(_state())
    assert r.ready and r.failed_checks == ()
    assert is_device_ready(_state(), expected_account_id="acct_9")


def test_wrong_foreground_account_is_red_line():
    # 红线：前台账号 ≠ 目标账号 → 绝不发布（否则发到别人号上）
    r = _readiness(_state(foreground_account_id="acct_OTHER"))
    assert not r.ready
    assert DeviceCheck.WRONG_FOREGROUND_ACCOUNT in r.failed_checks


def test_each_check_fails():
    cases = {
        DeviceCheck.BATTERY_LOW: _state(battery_pct=5),
        DeviceCheck.STORAGE_LOW: _state(storage_free_mb=10),
        DeviceCheck.NETWORK_OFFLINE: _state(network_online=False),
        DeviceCheck.DEVICE_LOCKED: _state(unlocked=False),
    }
    for check, state in cases.items():
        r = _readiness(state)
        assert not r.ready and check in r.failed_checks


def test_app_version_gate():
    crit = DeviceReadinessCriteria(allowed_app_versions=("30.1", "30.2"))
    assert _readiness(_state(app_version="29.0"), criteria=crit).failed_checks == (
        DeviceCheck.APP_VERSION_UNSUPPORTED,)
    # 允许列表内 → 不报
    assert DeviceCheck.APP_VERSION_UNSUPPORTED not in _readiness(
        _state(app_version="30.2"), criteria=crit).failed_checks
    # 无列表 → 不检查版本
    assert _readiness(_state(app_version="whatever")).ready


def test_multiple_failures_collected():
    r = _readiness(_state(battery_pct=1, unlocked=False, network_online=False,
                           foreground_account_id="x"))
    assert set(r.failed_checks) == {
        DeviceCheck.BATTERY_LOW, DeviceCheck.DEVICE_LOCKED,
        DeviceCheck.NETWORK_OFFLINE, DeviceCheck.WRONG_FOREGROUND_ACCOUNT,
    }


def test_custom_criteria_thresholds():
    crit = DeviceReadinessCriteria(min_battery_pct=90, min_storage_free_mb=5000)
    r = _readiness(_state(battery_pct=80, storage_free_mb=2000), criteria=crit)
    assert {DeviceCheck.BATTERY_LOW, DeviceCheck.STORAGE_LOW} <= set(r.failed_checks)


# --- §7.2 单设备单 Job ---------------------------------------------------

def test_single_job_per_device():
    assert can_dispatch_to_device("d1", [])
    assert can_dispatch_to_device("d1", ["d2", "d3"])
    assert not can_dispatch_to_device("d1", ["d1"])
    assert not can_dispatch_to_device("d1", ["d1", "d2"])
