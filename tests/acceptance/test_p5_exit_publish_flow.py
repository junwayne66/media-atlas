"""P5 Exit —— 测试账号端到端发布（Fake-first）+ 发布前预检确认账号（§13）。

覆盖 VF-502 预检 + VF-503/504 executor 生命周期：预检 publishable → 建 Job → 提交 →
查状态 → SUCCEEDED + 保存外部 ID。四个 Fake executor（TikTok/抖音/浏览器/Android）各跑通。
非空跑护栏：预检不过（未授权/账号封禁/媒体不符）绝不 publishable。
"""

from __future__ import annotations

from datetime import UTC, datetime

from p5_flow import make_uploading_job, run_publish

from videoforge_contracts import (
    AccountStatus,
    AuthStatus,
    ClientReviewStatus,
    PlatformPublishSpec,
    PublishConnectorCapability,
    PublishMediaProbe,
    PublishMetadata,
    PublishMethod,
    PublishPlatform,
    PublishState,
)
from videoforge_domain import is_publishable, run_preflight, validate_publish_job
from videoforge_provider_sdk import (
    FakeAndroidPublishExecutor,
    FakeBrowserPublishExecutor,
    FakeDouyinPublishExecutor,
    FakeTikTokPublishExecutor,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _spec(platform=PublishPlatform.TIKTOK) -> PlatformPublishSpec:
    return PlatformPublishSpec(
        platform=platform,
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
    )


def _probe() -> PublishMediaProbe:
    return PublishMediaProbe(
        width=1080,
        height=1920,
        aspect_ratio="9:16",
        video_codec="h264",
        audio_codec="aac",
        container="mp4",
        file_size_bytes=50_000_000,
        duration_ms=30000,
    )


def _cap(platform=PublishPlatform.TIKTOK, method=PublishMethod.OFFICIAL_API, **over):
    base = dict(
        platform=platform,
        method=method,
        available=True,
        auth_status=AuthStatus.AUTHORIZED,
        client_review_status=ClientReviewStatus.APPROVED,
        account_status=AccountStatus.ACTIVE,
    )
    base.update(over)
    return PublishConnectorCapability(**base)


def _meta() -> PublishMetadata:
    return PublishMetadata(title="AI 芯片新品", tags=["ai"], language="zh-CN")


# --- 发布前预检确认账号（§13）------------------------------------------


def test_preflight_passes_then_publishes_end_to_end():
    report = run_preflight(_probe(), _meta(), _spec(), _cap(), id="pf", created_at=_T0)
    assert report.publishable and is_publishable(report)
    # 预检过 → 端到端发布
    job, sub = run_publish(FakeTikTokPublishExecutor())
    assert job.state is PublishState.SUCCEEDED
    assert job.external_post_id
    assert validate_publish_job(job) == []


def test_preflight_blocks_unauthorized_and_suspended():
    # 发布前必须能确认账号：未授权 / 账号封禁 → 不可发布
    assert not run_preflight(
        _probe(),
        _meta(),
        _spec(),
        _cap(auth_status=AuthStatus.UNAUTHORIZED),
        id="pf",
        created_at=_T0,
    ).publishable
    assert not run_preflight(
        _probe(),
        _meta(),
        _spec(),
        _cap(account_status=AccountStatus.SUSPENDED),
        id="pf",
        created_at=_T0,
    ).publishable


def test_preflight_blocks_media_mismatch():
    # 媒体不符（编码/宽高比/时长）→ 不可发布
    bad_codec = _probe().model_copy(update={"video_codec": "vp9"})
    assert not run_preflight(
        bad_codec, _meta(), _spec(), _cap(), id="pf", created_at=_T0
    ).publishable
    bad_dur = _probe().model_copy(update={"duration_ms": 900})
    assert not run_preflight(bad_dur, _meta(), _spec(), _cap(), id="pf", created_at=_T0).publishable


def test_all_four_fake_adapters_publish_end_to_end():
    execs = {
        "tiktok": FakeTikTokPublishExecutor(),
        "douyin": FakeDouyinPublishExecutor(),
        "browser": FakeBrowserPublishExecutor(),  # allowed=True default
        "android": FakeAndroidPublishExecutor(),  # device_ready=True default
    }
    for name, ex in execs.items():
        job = make_uploading_job(job_id=f"j-{name}")
        final, sub = run_publish(ex, job=job)
        assert final.state is PublishState.SUCCEEDED, name
        assert final.external_post_id, name
        assert validate_publish_job(final) == [], name
