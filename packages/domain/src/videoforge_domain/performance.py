"""效果反馈 domain（docs/modules/44 §10 快照计划 + 限流 + null 语义 + 完整性护栏）。纯函数。

- **快照计划**：`due_snapshot_ages` / `next_snapshot_age` / `next_snapshot_time` /
  `record_capture` / `is_schedule_complete`——按 §10 的 1/3/6/24/72h/7d 年龄点，据 published_at
  与 now 算"现在该抓哪个""下一个 Temporal Timer 何时触发""标记已抓"。
- **限流**：`can_fetch_now` / `next_allowed_fetch_time`——按连接器上报的
  `min_seconds_between_calls` 排程，不超平台限流。
- **null 语义（§10 红线）**：所有完整性检查与派生指标都**把 None 当"未知"跳过，绝不当 0**。
  `relative_to_baseline`（§11 账号内相对指标的原语）在任一端为 None 或基线为 0 时返 None，
  而不是拿 0 顶替。`validate_performance_snapshot` 的跨字段一致性检查全部在两端非空时才触发。

时刻/日期由调用方传入（无时钟依赖，可复现）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from videoforge_contracts import PerformanceSnapshot, SnapshotSchedule

# §10 建议快照年龄点（小时）：发布后 1h、3h、6h、24h、72h、7d(=168h)。
DEFAULT_SNAPSHOT_AGES_HOURS: tuple[float, ...] = (1.0, 3.0, 6.0, 24.0, 72.0, 168.0)


# --- 快照计划 ---------------------------------------------------------------

def elapsed_hours(published_at: datetime, now: datetime) -> float:
    """发布至 now 经过的小时数（可为负，若 now 早于发布）。"""
    return (now - published_at).total_seconds() / 3600.0


def due_snapshot_ages(
    schedule: SnapshotSchedule, now: datetime, *, tolerance_hours: float = 0.0
) -> list[float]:
    """现在（now）该抓的年龄点：已到龄（elapsed ≥ age − 容差）且尚未抓过的 planned 年龄，升序。"""
    elapsed = elapsed_hours(schedule.published_at, now)
    captured = set(schedule.captured_ages_hours)
    return sorted(
        age
        for age in schedule.planned_ages_hours
        if age not in captured and elapsed >= age - tolerance_hours
    )


def next_snapshot_age(schedule: SnapshotSchedule) -> float | None:
    """下一个尚未抓取的最小 planned 年龄；全部抓完 → None。"""
    captured = set(schedule.captured_ages_hours)
    remaining = [a for a in schedule.planned_ages_hours if a not in captured]
    return min(remaining) if remaining else None


def next_snapshot_time(schedule: SnapshotSchedule) -> datetime | None:
    """下一个快照的绝对时刻（published_at + 下一个未抓年龄）——Temporal Timer 目标；全抓完 None。"""
    age = next_snapshot_age(schedule)
    if age is None:
        return None
    return schedule.published_at + timedelta(hours=age)


def record_capture(schedule: SnapshotSchedule, age_hours: float) -> SnapshotSchedule:
    """标记某年龄点已抓取（不可变返回新对象）。年龄必须是 planned 之一；重复标记幂等。"""
    if age_hours not in set(schedule.planned_ages_hours):
        raise ValueError(f"{age_hours} 不在 planned_ages_hours 中，不能标记为已抓取")
    if age_hours in set(schedule.captured_ages_hours):
        return schedule
    return schedule.model_copy(
        update={"captured_ages_hours": [*schedule.captured_ages_hours, age_hours]}
    )


def is_schedule_complete(schedule: SnapshotSchedule) -> bool:
    """所有 planned 年龄点都已抓取。"""
    return set(schedule.planned_ages_hours) <= set(schedule.captured_ages_hours)


# --- 限流 -------------------------------------------------------------------

def can_fetch_now(
    last_fetch_at: datetime | None, now: datetime, min_seconds_between_calls: int
) -> bool:
    """距上次调用是否已满足最小间隔。从未调用（last=None）→ True。"""
    if last_fetch_at is None:
        return True
    return (now - last_fetch_at).total_seconds() >= min_seconds_between_calls


def next_allowed_fetch_time(
    last_fetch_at: datetime | None, min_seconds_between_calls: int
) -> datetime | None:
    """下一次允许调用的最早时刻；从未调用 → None（可立即调用）。"""
    if last_fetch_at is None:
        return None
    return last_fetch_at + timedelta(seconds=min_seconds_between_calls)


# --- null 语义：派生指标（§11 账号内相对指标原语）---------------------------

def relative_to_baseline(value: float | None, baseline: float | None) -> float | None:
    """账号内相对指标 value/baseline（§11）。**null 绝不当 0**：任一端 None 或基线为 0 → None。"""
    if value is None or baseline is None or baseline == 0:
        return None
    return value / baseline


# --- 快照完整性护栏（全部 null-aware：None=未知，跳过，绝不当 0）-------------

class PerformanceIssueKind(StrEnum):
    AGE_NEGATIVE = "AGE_NEGATIVE"  # age_hours < 0（合同已拦，纵深防御）
    RATE_OUT_OF_RANGE = "RATE_OUT_OF_RANGE"  # 比率 ∉ [0,1]（合同已拦，纵深防御）
    NEGATIVE_METRIC = "NEGATIVE_METRIC"  # 计数为负（合同已拦，纵深防御）
    ENGAGEMENT_EXCEEDS_VIEWS = "ENGAGEMENT_EXCEEDS_VIEWS"  # 互动 > 播放（两端非空）
    VIEWS_EXCEED_IMPRESSIONS = "VIEWS_EXCEED_IMPRESSIONS"  # 播放 > 曝光（两端非空）
    COMPLETION_RATE_WITHOUT_VIEWS = "COMPLETION_RATE_WITHOUT_VIEWS"  # 有完成率却 0 播放（矛盾）


@dataclass(frozen=True)
class PerformanceIssue:
    kind: PerformanceIssueKind
    ref: str
    detail: str


_COUNT_FIELDS = (
    "views", "watch_time_ms", "avg_watch_time_ms", "likes", "comments",
    "shares", "saves", "follows", "impressions",
)
_ENGAGEMENT_FIELDS = ("likes", "comments", "shares", "saves")


def validate_performance_snapshot(snapshot: PerformanceSnapshot) -> list[PerformanceIssue]:
    """快照完整性护栏。**每条跨字段检查都在相关字段全非空时才触发**——缺失(None)一律跳过，
    绝不把 null 当 0 参与比较（§10 red line）。前三类是合同已拦的纵深防御。"""
    issues: list[PerformanceIssue] = []
    ref = snapshot.platform_post_id

    if snapshot.age_hours < 0:
        issues.append(PerformanceIssue(PerformanceIssueKind.AGE_NEGATIVE, ref,
                                        f"age_hours={snapshot.age_hours} < 0"))

    for field in _COUNT_FIELDS:
        v = getattr(snapshot, field)
        if v is not None and v < 0:
            issues.append(PerformanceIssue(PerformanceIssueKind.NEGATIVE_METRIC, ref,
                                            f"{field}={v} < 0"))
    for field in ("completion_rate", "click_through_rate"):
        v = getattr(snapshot, field)
        if v is not None and not (0.0 <= v <= 1.0):
            issues.append(PerformanceIssue(PerformanceIssueKind.RATE_OUT_OF_RANGE, ref,
                                            f"{field}={v} ∉ [0,1]"))

    # 互动 > 播放：仅在该互动字段与 views 都非空时比较（views=None → 未知 → 跳过，不当 0）。
    if snapshot.views is not None:
        for field in _ENGAGEMENT_FIELDS:
            v = getattr(snapshot, field)
            if v is not None and v > snapshot.views:
                issues.append(PerformanceIssue(
                    PerformanceIssueKind.ENGAGEMENT_EXCEEDS_VIEWS, ref,
                    f"{field}={v} > views={snapshot.views}"))

    # 播放 > 曝光：两端非空才比较。
    if (snapshot.views is not None and snapshot.impressions is not None
            and snapshot.views > snapshot.impressions):
        issues.append(PerformanceIssue(
            PerformanceIssueKind.VIEWS_EXCEED_IMPRESSIONS, ref,
            f"views={snapshot.views} > impressions={snapshot.impressions}"))

    # 有完成率却 views 明确为 0（矛盾）。views=None（未知）→ 不触发（这正是 null≠0）。
    if snapshot.completion_rate is not None and snapshot.views == 0:
        issues.append(PerformanceIssue(
            PerformanceIssueKind.COMPLETION_RATE_WITHOUT_VIEWS, ref,
            f"completion_rate={snapshot.completion_rate} 但 views=0"))

    return issues


def is_valid_performance_snapshot(snapshot: PerformanceSnapshot) -> bool:
    return not validate_performance_snapshot(snapshot)
