"""文字跟踪 + 多帧投票 + 类型分类（docs/modules/41 §8）。纯函数，逐位可重放。

- track_text_observations：逐帧 OCR 检测按时间 + IoU 贪心关联成稳定 TextTrack，
  大时间间隔断轨——同一区域轻微抖动不会分裂成多轨（§8.3）。
- 多帧投票：同轨多帧文本取多数，抵消个别帧误识（§8.5）。
- classify_kind：按位置/尺寸/持久度启发式分字幕/标题/UI/水印/场景文字（§8.4）。

不改输入、不触网、不依赖任何 OCR 引擎。
"""

from __future__ import annotations

from videoforge_contracts import BBox, TextObservation, TextTrack, TextTrackKind

_IOU_THRESHOLD = 0.4
_GAP_MS = 1200
_MOTION_THRESHOLD = 0.05  # 中心位移超此比例视为 MOVING
_REVIEW_CONFIDENCE = 0.6


def iou(a: BBox, b: BBox) -> float:
    """两个归一化边界框的交并比。"""
    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = ix * iy
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def vote_text(observations: list[TextObservation]) -> tuple[str, float]:
    """多帧多数投票定文本 + 该文本的平均置信度。确定性：数量→总置信→字典序。"""
    by_text: dict[str, list[float]] = {}
    for o in observations:
        by_text.setdefault(o.text, []).append(o.confidence)
    text, confs = min(by_text.items(), key=lambda kv: (-len(kv[1]), -sum(kv[1]), kv[0]))
    return text, sum(confs) / len(confs)


def _representative(observations: list[TextObservation]) -> tuple[float, float, float, float]:
    n = len(observations)
    x = sum(o.bbox.x for o in observations) / n
    y = sum(o.bbox.y for o in observations) / n
    w = sum(o.bbox.w for o in observations) / n
    h = sum(o.bbox.h for o in observations) / n
    return x, y, w, h


def _motion(observations: list[TextObservation]) -> str:
    if len(observations) < 2:
        return "STATIC"
    centers = [(o.bbox.x + o.bbox.w / 2, o.bbox.y + o.bbox.h / 2) for o in observations]
    max_dx = max(abs(cx - centers[0][0]) for cx, _ in centers)
    max_dy = max(abs(cy - centers[0][1]) for _, cy in centers)
    return "MOVING" if max(max_dx, max_dy) > _MOTION_THRESHOLD else "STATIC"


def classify_kind(
    observations: list[TextObservation], *, total_duration_ms: int | None = None
) -> TextTrackKind:
    """按代表框位置/尺寸/持久度分类（启发式，41 §8.4）。"""
    x, y, w, h = _representative(observations)
    cy = y + h / 2
    small = w < 0.25 and h < 0.12
    corner = (x < 0.12 or (x + w) > 0.88) and (y < 0.15 or (y + h) > 0.85)
    duration = observations[-1].frame_time_ms - observations[0].frame_time_ms
    persistent = (
        total_duration_ms is not None
        and total_duration_ms > 0
        and duration / total_duration_ms > 0.6
    )

    if small and corner and persistent:
        return TextTrackKind.BRAND_MARK  # 小、角落、持久 → 水印/品牌标
    if small and corner:
        return TextTrackKind.UI  # 小、角落、短 → 界面元素
    if cy > 0.72 and w > 0.3:
        return TextTrackKind.CAPTION  # 底部、宽 → 字幕
    if cy < 0.35 and h > 0.1:
        return TextTrackKind.TITLE  # 顶部、大 → 标题
    if 0.55 < cy < 0.85 and x < 0.5:
        return TextTrackKind.LOWER_THIRD  # 下三分带、左侧 → 信息条
    if 0.3 <= cy <= 0.72:
        return TextTrackKind.SCENE_TEXT  # 画面中部 → 场景内文字
    return TextTrackKind.UNKNOWN


def track_text_observations(
    observations: list[TextObservation],
    *,
    iou_threshold: float = _IOU_THRESHOLD,
    gap_ms: int = _GAP_MS,
    total_duration_ms: int | None = None,
) -> list[TextTrack]:
    """逐帧检测 → 稳定 TextTrack 列表。IoU 贪心关联；关联条件：IoU≥阈值 且（时间在 gap
    内 或 文本相同）。后者让稀疏采样的持久水印跨大间隔仍聚成一条轨，而不同文本 + 大间隔
    仍断轨（避免把先后出现的两条不同字幕并成一条）。"""
    ordered = sorted(observations, key=lambda o: (o.frame_time_ms, o.bbox.x, o.bbox.y))
    tracks: list[list[TextObservation]] = []

    for o in ordered:
        best: list[TextObservation] | None = None
        best_iou = iou_threshold
        for track in tracks:
            last = track[-1]
            within_gap = o.frame_time_ms - last.frame_time_ms <= gap_ms
            same_text = o.text == last.text
            if not (within_gap or same_text):
                continue  # 不同文本且间隔过大 → 视为新对象
            i = iou(o.bbox, last.bbox)
            if i >= best_iou:
                best, best_iou = track, i
        if best is None:
            tracks.append([o])
        else:
            best.append(o)

    all_tracks = tracks
    # 按起始时间稳定排序，便于确定性 id
    all_tracks.sort(key=lambda t: (t[0].frame_time_ms, t[0].bbox.x, t[0].bbox.y))

    result: list[TextTrack] = []
    for idx, obs_list in enumerate(all_tracks):
        text, conf = vote_text(obs_list)
        result.append(
            TextTrack(
                id=f"tt-{idx}",
                kind=classify_kind(obs_list, total_duration_ms=total_duration_ms),
                text=text,
                start_ms=obs_list[0].frame_time_ms,
                end_ms=obs_list[-1].frame_time_ms,
                confidence=conf,
                observations=obs_list,
                motion=_motion(obs_list),
                low_confidence=conf < _REVIEW_CONFIDENCE,
            )
        )
    return result
