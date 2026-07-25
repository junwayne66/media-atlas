"""VF-502 发布前检查 domain 测试：媒体/元数据/授权检查 + §3 方法阶梯 + 发布门。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    AccountStatus,
    AuthStatus,
    ClientReviewStatus,
    PlatformPublishSpec,
    PreflightCheck,
    PublishConnectorCapability,
    PublishMediaProbe,
    PublishMetadata,
    PublishMethod,
    PublishPlatform,
    ReviewSeverity,
)
from videoforge_domain import (
    is_publishable,
    publish_preflight_gate,
    run_preflight,
    select_publish_method,
    validate_preflight_report,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _spec(**over) -> PlatformPublishSpec:
    base = dict(
        platform=PublishPlatform.TIKTOK,
        allowed_aspect_ratios=["9:16"],
        min_width=360,
        min_height=640,
        max_width=1080,
        max_height=1920,
        allowed_video_codecs=["h264"],
        allowed_audio_codecs=["aac"],
        allowed_containers=["mp4"],
        max_file_size_bytes=500_000_000,
        min_duration_ms=3000,
        max_duration_ms=600_000,
        title_max_len=150,
        description_max_len=2200,
        max_tags=20,
        tag_max_len=100,
        banned_title_chars=["<", ">"],
    )
    base.update(over)
    return PlatformPublishSpec(**base)


def _probe(**over) -> PublishMediaProbe:
    base = dict(
        width=1080,
        height=1920,
        aspect_ratio="9:16",
        video_codec="h264",
        audio_codec="aac",
        container="mp4",
        file_size_bytes=50_000_000,
        duration_ms=30000,
    )
    base.update(over)
    return PublishMediaProbe(**base)


def _meta(**over) -> PublishMetadata:
    base = dict(title="AI 芯片新品", description="desc", tags=["ai", "chip"], language="zh-CN")
    base.update(over)
    return PublishMetadata(**base)


def _cap(**over) -> PublishConnectorCapability:
    base = dict(
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        available=True,
        auth_status=AuthStatus.AUTHORIZED,
        client_review_status=ClientReviewStatus.APPROVED,
        account_status=AccountStatus.ACTIVE,
    )
    base.update(over)
    return PublishConnectorCapability(**base)


def _run(**over):
    probe = over.pop("probe", _probe())
    meta = over.pop("meta", _meta())
    spec = over.pop("spec", _spec())
    cap = over.pop("cap", _cap())
    return run_preflight(probe, meta, spec, cap, id="pf", created_at=_T0)


def _checks(report) -> set:
    return {(f.check, f.severity) for f in report.findings}


# --- 通过 -----------------------------------------------------------------


def test_clean_package_is_publishable():
    r = _run()
    assert r.publishable and r.findings == []
    assert is_publishable(r)


# --- 媒体检查 -------------------------------------------------------------


def test_each_media_check_fails():
    cases = {
        PreflightCheck.RESOLUTION: _probe(width=2000, height=2000),
        PreflightCheck.ASPECT_RATIO: _probe(aspect_ratio="1:1"),
        PreflightCheck.VIDEO_CODEC: _probe(video_codec="vp9"),
        PreflightCheck.AUDIO_CODEC: _probe(audio_codec="opus"),
        PreflightCheck.CONTAINER: _probe(container="webm"),
        PreflightCheck.FILE_SIZE: _probe(file_size_bytes=600_000_000),
        PreflightCheck.DURATION: _probe(duration_ms=1000),
    }
    for check, probe in cases.items():
        r = _run(probe=probe)
        assert (check, ReviewSeverity.ERROR) in _checks(r), check
        assert not r.publishable


def test_capability_file_size_cap_is_tighter():
    # 连接器上限比平台更严 → 用更严的
    r = _run(probe=_probe(file_size_bytes=200_000_000), cap=_cap(max_file_size_bytes=100_000_000))
    assert (PreflightCheck.FILE_SIZE, ReviewSeverity.ERROR) in _checks(r)


# --- 元数据检查（§9）-----------------------------------------------------


def test_metadata_checks_fail():
    assert (PreflightCheck.TITLE_LENGTH, ReviewSeverity.ERROR) in _checks(
        _run(meta=_meta(title="x" * 200))
    )
    assert (PreflightCheck.TITLE_BANNED_CHARS, ReviewSeverity.ERROR) in _checks(
        _run(meta=_meta(title="hi <script>"))
    )
    assert (PreflightCheck.DESCRIPTION_LENGTH, ReviewSeverity.ERROR) in _checks(
        _run(meta=_meta(description="d" * 3000))
    )
    assert (PreflightCheck.TAG_COUNT, ReviewSeverity.ERROR) in _checks(
        _run(meta=_meta(tags=[f"t{i}" for i in range(30)]))
    )
    assert (PreflightCheck.TAG_LENGTH, ReviewSeverity.ERROR) in _checks(
        _run(meta=_meta(tags=["x" * 200]))
    )


# --- 授权/审核/账号（红线）----------------------------------------------


def test_unauthorized_blocks():
    for st in (AuthStatus.UNAUTHORIZED, AuthStatus.PENDING_REVIEW, AuthStatus.EXPIRED):
        r = _run(cap=_cap(auth_status=st))
        assert (PreflightCheck.AUTH_STATUS, ReviewSeverity.ERROR) in _checks(r)
        assert not r.publishable


def test_unaudited_client_is_warning_not_block():
    # §3.1：未审核客户端可发但可见性受限 → WARNING，仍 publishable
    for st in (ClientReviewStatus.UNAUDITED, ClientReviewStatus.UNDER_REVIEW):
        r = _run(cap=_cap(client_review_status=st))
        assert (PreflightCheck.REVIEW_STATUS, ReviewSeverity.WARNING) in _checks(r)
        assert r.publishable  # WARNING 不阻塞


def test_suspended_account_is_fatal():
    r = _run(cap=_cap(account_status=AccountStatus.SUSPENDED))
    assert (PreflightCheck.ACCOUNT_STATUS, ReviewSeverity.FATAL) in _checks(r)
    assert not r.publishable


def test_restricted_account_is_warning():
    r = _run(cap=_cap(account_status=AccountStatus.RESTRICTED))
    assert (PreflightCheck.ACCOUNT_STATUS, ReviewSeverity.WARNING) in _checks(r)
    assert r.publishable


def test_method_unavailable_blocks():
    r = _run(cap=_cap(available=False))
    assert (PreflightCheck.METHOD_UNAVAILABLE, ReviewSeverity.ERROR) in _checks(r)
    assert not r.publishable


def test_platform_mismatch_is_fatal():
    r = _run(cap=_cap(platform=PublishPlatform.DOUYIN))  # spec 是 TIKTOK
    assert any(f.severity is ReviewSeverity.FATAL for f in r.findings)
    assert not r.publishable


# --- 发布门 ---------------------------------------------------------------


def test_gate_and_report_consistency():
    clean = _run()
    assert publish_preflight_gate(clean.findings) is True
    assert validate_preflight_report(clean) == []
    warn_only = _run(cap=_cap(account_status=AccountStatus.RESTRICTED))
    assert warn_only.publishable and validate_preflight_report(warn_only) == []
    blocked = _run(cap=_cap(auth_status=AuthStatus.UNAUTHORIZED))
    assert not blocked.publishable and validate_preflight_report(blocked) == []


# --- §3 方法阶梯 ----------------------------------------------------------


def test_select_prefers_official_api():
    caps = [
        _cap(method=PublishMethod.MANUAL_EXPORT, auth_status=AuthStatus.UNAUTHORIZED),
        _cap(method=PublishMethod.BROWSER_AUTOMATION),
        _cap(method=PublishMethod.OFFICIAL_API),
    ]
    assert select_publish_method(caps).method is PublishMethod.OFFICIAL_API


def test_select_falls_to_manual_when_official_unavailable():
    caps = [
        _cap(method=PublishMethod.OFFICIAL_API, available=False),
        _cap(method=PublishMethod.MANUAL_EXPORT, auth_status=AuthStatus.UNAUTHORIZED),
    ]
    assert select_publish_method(caps).method is PublishMethod.MANUAL_EXPORT


def test_select_skips_unauthorized_and_suspended():
    caps = [
        _cap(method=PublishMethod.OFFICIAL_API, auth_status=AuthStatus.UNAUTHORIZED),
        _cap(method=PublishMethod.BROWSER_AUTOMATION, account_status=AccountStatus.SUSPENDED),
    ]
    assert select_publish_method(caps) is None  # 无 manual 兜底 → None


def test_select_none_when_empty():
    assert select_publish_method([]) is None


def test_select_picks_usable_among_duplicate_methods():
    # 同方法多条：前面不可用的不遮蔽后面可用的（first-usable-wins）
    caps = [
        _cap(method=PublishMethod.OFFICIAL_API, auth_status=AuthStatus.UNAUTHORIZED),
        _cap(method=PublishMethod.OFFICIAL_API, auth_status=AuthStatus.AUTHORIZED),
    ]
    sel = select_publish_method(caps)
    assert sel is not None and sel.auth_status is AuthStatus.AUTHORIZED
