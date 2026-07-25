"""P5 Exit —— 任一版本修改使旧审批失效（§13 / §1.2）+ 账号确认（§7.2 前台账号）。

VF-501：审批绑定到确切版本+内容，一改即失效。VF-506：真机前台账号必须正是目标账号。
"""

from __future__ import annotations

from datetime import UTC, datetime

from videoforge_contracts import (
    ReviewDecision,
    ReviewDecisionKind,
    ReviewScope,
)
from videoforge_domain import (
    DeviceCheck,
    DeviceState,
    check_device_readiness,
    compute_approval_signature,
    is_approval_valid,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _approved(version: int, digest: str) -> ReviewDecision:
    sig = compute_approval_signature(
        entity_id="var_1",
        entity_version=version,
        content_digest=digest,
        decision=ReviewDecisionKind.APPROVED,
        scope="VARIANT",
        reviewer_id="u1",
        policy_snapshot_id="p1",
    )
    return ReviewDecision(
        id="rd1",
        decision=ReviewDecisionKind.APPROVED,
        scope=ReviewScope.VARIANT,
        entity_id="var_1",
        entity_version=version,
        content_digest=digest,
        reviewer_id="u1",
        policy_snapshot_id="p1",
        signature=sig,
        created_at=_T0,
    )


# --- §13：修改使旧审批失效 --------------------------------------------


def test_approval_valid_until_modified():
    d = _approved(version=7, digest="abc")
    assert is_approval_valid(d, current_version=7, current_content_digest="abc")
    # 版本变（重新渲染）→ 失效
    assert not is_approval_valid(d, current_version=8, current_content_digest="abc")
    # 内容变（改文案）→ 失效
    assert not is_approval_valid(d, current_version=7, current_content_digest="new")
    # 实体绑定（换了对象）→ 失效
    assert not is_approval_valid(
        d, current_version=7, current_content_digest="abc", current_entity_id="var_OTHER"
    )


# --- §7.2：发布前确认账号（真机前台账号红线）------------------------


def test_wrong_foreground_account_blocks_publish():
    good = DeviceState(
        device_id="d1",
        battery_pct=80,
        storage_free_mb=2000,
        network_online=True,
        unlocked=True,
        app_version="30.1",
        foreground_account_id="acct_9",
    )
    assert check_device_readiness(good, expected_account_id="acct_9").ready
    # 前台是别的账号 → 绝不发布（防发错号）
    bad = DeviceState(
        device_id="d1",
        battery_pct=80,
        storage_free_mb=2000,
        network_online=True,
        unlocked=True,
        app_version="30.1",
        foreground_account_id="acct_OTHER",
    )
    r = check_device_readiness(bad, expected_account_id="acct_9")
    assert not r.ready
    assert DeviceCheck.WRONG_FOREGROUND_ACCOUNT in r.failed_checks
