from datetime import UTC, datetime

from videoforge_contracts import (
    AcquisitionAttemptSummary,
    AcquisitionSummary,
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
)
from videoforge_persistence import new_id

T0 = datetime(2026, 7, 25, 0, 0, 0, tzinfo=UTC)


def make_url_asset(**overrides) -> SourceAsset:
    values = {
        "id": new_id(),
        "kind": SourceAssetKind.URL,
        "original_input": "https://www.douyin.com/video/7412345678901234567",
        "platform": "douyin",
        "content_id": "7412345678901234567",
        "canonical_url": "https://www.douyin.com/video/7412345678901234567",
        "disposition": SourceDisposition.MANUAL_FALLBACK,
        "reason": "实时下载未配置；请人工下载后关联",
        "error_code": "UNCONFIGURED",
        "acquisition": AcquisitionSummary(
            tool_name="download.router",
            attempts=[
                AcquisitionAttemptSummary(
                    connector="download.f2", status="unconfigured", error_code="UNCONFIGURED"
                )
            ],
            manual_fallback=True,
        ),
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return SourceAsset(**values)


def make_file_asset(**overrides) -> SourceAsset:
    values = {
        "id": new_id(),
        "kind": SourceAssetKind.LOCAL_FILE,
        "original_input": "/media/demo.mp4",
        "platform": "manual",
        "content_id": "demo.mp4",
        "canonical_url": "/media/demo.mp4",
        "disposition": SourceDisposition.IMPORTED,
        "reason": "本地原片已导入",
        "local_path": "/media/demo.mp4",
        "file_sha256": "a" * 64,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return SourceAsset(**values)
