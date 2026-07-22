"""文字跟踪/投票/分类：IoU 关联稳定、多帧投票纠错、类型分类、纯可重放。"""

from videoforge_contracts import BBox, TextObservation, TextTrackKind
from videoforge_domain import classify_kind, iou, track_text_observations, vote_text


def _obs(t, x, y, w, h, text, conf=0.9) -> TextObservation:
    return TextObservation(
        frame_time_ms=t, bbox=BBox(x=x, y=y, w=w, h=h), text=text, confidence=conf
    )


def test_iou_basic() -> None:
    a = BBox(x=0.0, y=0.0, w=0.5, h=0.5)
    assert iou(a, a) == 1.0
    assert iou(a, BBox(x=0.5, y=0.5, w=0.5, h=0.5)) == 0.0  # 不相交
    half = iou(a, BBox(x=0.25, y=0.0, w=0.5, h=0.5))
    assert 0.3 < half < 0.34  # 交 0.25*0.5，并 0.75*0.5 → 1/3


def test_jitter_stays_one_track() -> None:
    # 同一字幕逐帧轻微抖动（高 IoU）→ 应聚成 1 条轨，不分裂
    obs = [
        _obs(t, 0.2 + 0.005 * i, 0.82, 0.6, 0.08, "字幕")
        for i, t in enumerate([0, 400, 800, 1200])
    ]
    tracks = track_text_observations(obs)
    assert len(tracks) == 1
    assert tracks[0].start_ms == 0 and tracks[0].end_ms == 1200
    assert len(tracks[0].observations) == 4


def test_gap_splits_into_two_tracks() -> None:
    # 同位置但中间有大时间间隔 → 断成两轨
    obs = [_obs(0, 0.2, 0.82, 0.6, 0.08, "A"), _obs(5000, 0.2, 0.82, 0.6, 0.08, "B")]
    tracks = track_text_observations(obs, gap_ms=1200)
    assert len(tracks) == 2


def test_two_regions_two_tracks() -> None:
    # 同一时间两个不同位置（字幕 + 水印）→ 两轨
    obs = [
        _obs(0, 0.2, 0.82, 0.6, 0.08, "字幕"),
        _obs(0, 0.85, 0.05, 0.12, 0.05, "@brand"),
        _obs(400, 0.2, 0.82, 0.6, 0.08, "字幕"),
        _obs(400, 0.85, 0.05, 0.12, 0.05, "@brand"),
    ]
    tracks = track_text_observations(obs)
    assert len(tracks) == 2


def test_multiframe_voting_corrects_noise() -> None:
    # 4 帧中 1 帧误识，投票取多数
    obs = [
        _obs(0, 0.2, 0.82, 0.6, 0.08, "端侧推理", 0.9),
        _obs(400, 0.2, 0.82, 0.6, 0.08, "端测推理", 0.5),  # 误识
        _obs(800, 0.2, 0.82, 0.6, 0.08, "端侧推理", 0.92),
        _obs(1200, 0.2, 0.82, 0.6, 0.08, "端侧推理", 0.88),
    ]
    tracks = track_text_observations(obs)
    assert len(tracks) == 1
    assert tracks[0].text == "端侧推理"  # 多数胜出
    # 置信度取胜出文本各帧均值（不含误识帧）
    assert tracks[0].confidence > 0.85


def test_vote_text_deterministic_tie_break() -> None:
    obs = [_obs(0, 0.1, 0.1, 0.2, 0.1, "B", 0.9), _obs(1, 0.1, 0.1, 0.2, 0.1, "A", 0.9)]
    # 各 1 票、置信相同 → 字典序取 "A"
    assert vote_text(obs)[0] == "A"


def test_classify_kinds() -> None:
    caption = [_obs(0, 0.2, 0.82, 0.6, 0.08, "字幕")]
    title = [_obs(0, 0.15, 0.08, 0.7, 0.15, "大标题")]
    brand = [_obs(0, 0.86, 0.05, 0.12, 0.05, "@x"), _obs(50000, 0.86, 0.05, 0.12, 0.05, "@x")]
    ui = [_obs(0, 0.9, 0.02, 0.08, 0.04, "01:23")]
    scene = [_obs(0, 0.4, 0.45, 0.2, 0.1, "STORE")]
    assert classify_kind(caption) is TextTrackKind.CAPTION
    assert classify_kind(title) is TextTrackKind.TITLE
    assert classify_kind(brand, total_duration_ms=58000) is TextTrackKind.BRAND_MARK
    assert classify_kind(ui) is TextTrackKind.UI  # 小角落短
    assert classify_kind(scene) is TextTrackKind.SCENE_TEXT


def test_brand_mark_needs_persistence() -> None:
    # 小角落但短暂 → UI 而非 BRAND_MARK
    short = [_obs(0, 0.86, 0.05, 0.12, 0.05, "x"), _obs(500, 0.86, 0.05, 0.12, 0.05, "x")]
    assert classify_kind(short, total_duration_ms=58000) is TextTrackKind.UI


def test_motion_static_vs_moving() -> None:
    static = track_text_observations([_obs(t, 0.2, 0.82, 0.6, 0.08, "s") for t in (0, 400, 800)])
    # 渐进平移（小步高 IoU 保持一轨，累计中心位移 0.2 > 0.05 阈值）
    moving = track_text_observations(
        [
            _obs(t, 0.1 + 0.05 * i, 0.82, 0.4, 0.08, "m")
            for i, t in enumerate((0, 400, 800, 1200, 1600))
        ]
    )
    assert static[0].motion == "STATIC"
    assert len(moving) == 1  # 渐进移动仍是一条轨
    assert moving[0].motion == "MOVING"


def test_low_confidence_flag() -> None:
    lo = track_text_observations([_obs(t, 0.2, 0.82, 0.6, 0.08, "x", 0.4) for t in (0, 400)])
    assert lo[0].low_confidence is True


def test_replayable_and_no_mutation() -> None:
    obs = [_obs(t, 0.2, 0.82, 0.6, 0.08, "x") for t in (0, 400, 800)]
    before = list(obs)
    a = track_text_observations(obs)
    b = track_text_observations(obs)
    assert [t.model_dump() for t in a] == [t.model_dump() for t in b]  # 可重放
    assert obs == before  # 未改输入
