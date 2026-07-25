"""发布日程 + 副本幂等键（docs/modules/44 §4.4 WaitUntilSchedule + §5 重复帖子防护）。纯函数。

- `parse_publishing_window` / `is_within_publishing_window` / `next_publish_time`：把账号
  `publishing_window`（"HH:MM-HH:MM"，支持跨零点）算成 Temporal Timer 的目标时刻。
- `compute_copy_idempotency_key`：§5「用户明确选择发布副本才创建新幂等键」——`copy_index=0`
  即基础键（同内容去重、绝不重复发布），`copy_index≥1` 才派生**不同**键（有意的副本是新 Job）。

时刻/日期由调用方传入（无时钟依赖，可复现）。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from videoforge_contracts import PublishPlatform
from videoforge_domain.publish_job import compute_idempotency_key

# 立即发布的窗口标识（无需等待）
_IMMEDIATE = frozenset({"", "immediate", "now", "asap"})


def parse_publishing_window(window: str) -> tuple[time, time] | None:
    """解析 "HH:MM-HH:MM" → (start, end)。immediate/空 → None（立即）。非法 → 抛 ValueError。"""
    w = window.strip().lower()
    if w in _IMMEDIATE:
        return None
    if "-" not in w:
        raise ValueError(f"非法 publishing_window：{window!r}（应为 'HH:MM-HH:MM'）")
    a, b = w.split("-", 1)
    return _parse_hhmm(a.strip()), _parse_hhmm(b.strip())


def _parse_hhmm(s: str) -> time:
    hh, mm = s.split(":", 1)
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"非法时刻：{s!r}")
    return time(h, m)


def is_within_publishing_window(window: str, at: datetime) -> bool:
    """`at` 是否落在窗口内。immediate → 恒 True。支持跨零点窗口（如 22:00-02:00）。"""
    parsed = parse_publishing_window(window)
    if parsed is None:
        return True
    start, end = parsed
    now_t = at.time()
    if start <= end:  # 同日窗口
        return start <= now_t <= end
    # 跨零点：[start,24) ∪ [0,end]
    return now_t >= start or now_t <= end


def next_publish_time(window: str, after: datetime) -> datetime:
    """返回 ≥ after 且落在窗口内的最早时刻。immediate 或已在窗口内 → after（立即）。"""
    parsed = parse_publishing_window(window)
    if parsed is None or is_within_publishing_window(window, after):
        return after
    start, _ = parsed
    candidate = datetime.combine(after.date(), start, tzinfo=after.tzinfo)
    if candidate < after:  # 今天的开窗已过 → 明天
        candidate += timedelta(days=1)
    return candidate


def compute_copy_idempotency_key(
    *,
    account_id: str,
    platform: PublishPlatform,
    render_digest: str,
    metadata_digest: str,
    scheduled_window: str,
    copy_index: int = 0,
) -> str:
    """§5 副本键：copy_index=0 即基础键（去重）；≥1 才派生不同键（有意副本 = 新 Job）。"""
    if copy_index < 0:
        raise ValueError("copy_index 必须 ≥ 0")
    window = scheduled_window if copy_index == 0 else f"{scheduled_window}#copy{copy_index}"
    return compute_idempotency_key(
        account_id=account_id,
        platform=platform,
        render_digest=render_digest,
        metadata_digest=metadata_digest,
        scheduled_window=window,
    )
