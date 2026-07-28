from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from videoforge_contracts import (
    IngestJob,
    IngestJobEvent,
    IngestJobStatus,
    IngestJobType,
    RightsBasis,
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
    SourceProfile,
    SourceProfileStatus,
    SourcePublicMetadata,
    StageOutcome,
    StageOutcomeStatus,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def test_source_asset_metadata_only_and_rights_roundtrip() -> None:
    asset = SourceAsset(
        id="source-1",
        kind=SourceAssetKind.URL,
        original_input="https://www.douyin.com/video/7412345678901234567",
        platform="douyin",
        content_id="7412345678901234567",
        canonical_url="https://www.douyin.com/video/7412345678901234567",
        disposition=SourceDisposition.METADATA_ONLY,
        reason="公开元数据已采集，尚未授权获取媒体",
        public_metadata=SourcePublicMetadata(
            author_platform_id="author-1",
            author_name="fixture author",
            title="fixture title",
            duration_ms=1234,
            stats={"views": 12},
            raw_metadata={"fixture": "board_response.json"},
        ),
        rights_basis=RightsBasis.UNKNOWN,
        discovered_at=NOW,
        last_seen_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    assert SourceAsset.model_validate_json(asset.model_dump_json()) == asset


def test_imported_source_can_reference_artifact_without_local_path() -> None:
    asset = SourceAsset(
        id="source-1",
        kind=SourceAssetKind.URL,
        original_input="https://www.douyin.com/video/7412345678901234567",
        platform="douyin",
        content_id="7412345678901234567",
        canonical_url="https://www.douyin.com/video/7412345678901234567",
        disposition=SourceDisposition.IMPORTED,
        reason="对象存储原片已验证",
        artifact_ids=["artifact-1"],
        rights_basis=RightsBasis.OWNED,
        created_at=NOW,
        updated_at=NOW,
    )
    assert asset.file_sha256 is None


@pytest.mark.parametrize(
    "payload",
    [
        {"cookie": "canary"},
        {"nested": {"Authorization": "Bearer canary"}},
        {"items": [{"refresh_token": "canary"}]},
    ],
)
def test_public_metadata_rejects_secret_shaped_keys(payload: dict) -> None:
    with pytest.raises(ValidationError, match="敏感字段"):
        SourcePublicMetadata(raw_metadata=payload)


def test_job_and_event_reject_secret_shaped_payloads() -> None:
    with pytest.raises(ValidationError, match="敏感字段"):
        IngestJob(
            id="job-1",
            job_type=IngestJobType.CONTENT_RESOLVE,
            status=IngestJobStatus.PENDING,
            platform="douyin",
            idempotency_key="resolve-1",
            payload={"headers": {"cookie": "canary"}},
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValidationError, match="敏感字段"):
        IngestJobEvent(
            id="event-1",
            job_id="job-1",
            event_type="job.failed",
            details={"access_token": "canary"},
            created_at=NOW,
        )


def test_stage_outcome_requires_error_for_non_success() -> None:
    with pytest.raises(ValidationError, match="error_code"):
        StageOutcome(status=StageOutcomeStatus.NEED_HUMAN)


def test_source_profile_handle_is_opaque_not_path() -> None:
    profile = SourceProfile(
        id="profile-1",
        platform="douyin",
        profile_key="douyin-default",
        display_name="本地抖音 Profile",
        credential_handle="profile_01HZZZZZ",
        status=SourceProfileStatus.UNCONFIGURED,
        created_at=NOW,
        updated_at=NOW,
    )
    assert profile.credential_handle == "profile_01HZZZZZ"
    for unsafe in ("/Users/me/profile", "file://profile", "../profile", "profile:key"):
        with pytest.raises(ValidationError):
            SourceProfile.model_validate({**profile.model_dump(), "credential_handle": unsafe})
