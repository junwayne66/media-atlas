"""Android 真机发布前置检查（docs/modules/44 §7.2）。纯函数。

VF-506 的安全逻辑（供 workflow + Fake adapter 共用）：

- `check_device_readiness(state, expected_account_id, criteria)`：§7.2 步 2 就绪门——电量/
  存储/网络/解锁/App 版本/**前台账号**。**红线：前台账号 ≠ 目标账号 → 绝不发布**
  （否则发到别人号上）。
- `can_dispatch_to_device(device_id, busy)`：§7.2「单设备同时只运行一个发布 Job」。

真实 Appium/ADB 驱动真实设备是 stop-condition，本层只做纯就绪判定，不触真实设备。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum


class DeviceCheck(StrEnum):
    BATTERY_LOW = "BATTERY_LOW"
    STORAGE_LOW = "STORAGE_LOW"
    NETWORK_OFFLINE = "NETWORK_OFFLINE"
    DEVICE_LOCKED = "DEVICE_LOCKED"
    APP_VERSION_UNSUPPORTED = "APP_VERSION_UNSUPPORTED"
    # 红线：前台登录的账号不是目标账号 → 会发到错号
    WRONG_FOREGROUND_ACCOUNT = "WRONG_FOREGROUND_ACCOUNT"


@dataclass(frozen=True)
class DeviceState:
    """真机当前观测状态（来自 ADB/Appium 诊断；Fake/真实适配器产出）。"""

    device_id: str
    battery_pct: int
    storage_free_mb: int
    network_online: bool
    unlocked: bool
    app_version: str
    foreground_account_id: str


@dataclass(frozen=True)
class DeviceReadinessCriteria:
    min_battery_pct: int = 20
    min_storage_free_mb: int = 500
    require_unlocked: bool = True
    require_network: bool = True
    # 若非空，app_version 必须在其中（App 版本更新须 Canary 先过，§7.2）
    allowed_app_versions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeviceReadiness:
    ready: bool
    failed_checks: tuple[DeviceCheck, ...] = ()


def check_device_readiness(
    state: DeviceState,
    *,
    expected_account_id: str,
    criteria: DeviceReadinessCriteria | None = None,
) -> DeviceReadiness:
    """§7.2 步 2 设备就绪门。收集**全部**不达标项；任一不达标 → not ready。

    红线：`foreground_account_id != expected_account_id` → WRONG_FOREGROUND_ACCOUNT，
    绝不在错误账号上发布。
    """
    c = criteria or DeviceReadinessCriteria()
    failed: list[DeviceCheck] = []

    if state.battery_pct < c.min_battery_pct:
        failed.append(DeviceCheck.BATTERY_LOW)
    if state.storage_free_mb < c.min_storage_free_mb:
        failed.append(DeviceCheck.STORAGE_LOW)
    if c.require_network and not state.network_online:
        failed.append(DeviceCheck.NETWORK_OFFLINE)
    if c.require_unlocked and not state.unlocked:
        failed.append(DeviceCheck.DEVICE_LOCKED)
    if c.allowed_app_versions and state.app_version not in c.allowed_app_versions:
        failed.append(DeviceCheck.APP_VERSION_UNSUPPORTED)
    # 红线：前台账号必须正是目标账号
    if state.foreground_account_id != expected_account_id:
        failed.append(DeviceCheck.WRONG_FOREGROUND_ACCOUNT)

    return DeviceReadiness(ready=not failed, failed_checks=tuple(failed))


def is_device_ready(
    state: DeviceState, *, expected_account_id: str,
    criteria: DeviceReadinessCriteria | None = None,
) -> bool:
    return check_device_readiness(
        state, expected_account_id=expected_account_id, criteria=criteria,
    ).ready


def can_dispatch_to_device(device_id: str, busy_device_ids: Iterable[str]) -> bool:
    """§7.2：单设备同时只运行一个发布 Job。该设备已有在跑 Job → 不派发。"""
    return device_id not in set(busy_device_ids)


@dataclass(frozen=True)
class DeviceJobSlot:
    """一台设备的占用槽（供上层调度；本层只判定）。"""

    device_id: str
    active_job_ids: tuple[str, ...] = field(default_factory=tuple)
