import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videoforge_contracts import HealthState, StageOutcome, StageOutcomeStatus
from videoforge_edge_agent.ingest_provider import DouyinIngestProvider

REPO_ROOT = Path(__file__).parents[3]
FIXTURES = REPO_ROOT / "connectors/sources/douyin/fixtures"


def _provider() -> DouyinIngestProvider:
    return DouyinIngestProvider(fixture_dir=FIXTURES)


async def test_descriptor_and_offline_health() -> None:
    provider = _provider()
    assert provider.descriptor.name == "source.douyin"
    assert provider.descriptor.isolation_level == "L4"
    assert {"source.discover", "source.resolve", "source.acquire"}.issubset(
        provider.descriptor.capabilities
    )
    assert await provider.health_check() is HealthState.HEALTHY


async def test_fixture_discovery_ok_empty_drift_and_challenge() -> None:
    provider = _provider()
    cases = {
        "board_response.json": StageOutcomeStatus.SUCCEEDED,
        "empty_response.json": StageOutcomeStatus.EMPTY,
        "drift_response.json": StageOutcomeStatus.PERMANENT_ERROR,
        "challenge_response.json": StageOutcomeStatus.NEED_HUMAN,
    }
    for fixture, expected in cases.items():
        outcome = StageOutcome.model_validate(
            await provider.invoke(
                "source.discover",
                {
                    "platform": "douyin",
                    "query": "ai",
                    "fixture": fixture,
                    "max_items": 1,
                },
            )
        )
        assert outcome.status is expected
        if fixture == "board_response.json":
            assert outcome.result["result_count"] == 1


async def test_resolve_is_pure_and_short_link_requires_human() -> None:
    provider = _provider()
    canonical = StageOutcome.model_validate(
        await provider.invoke(
            "source.resolve",
            {"url": "https://www.douyin.com/video/7412345678901234567"},
        )
    )
    assert canonical.status is StageOutcomeStatus.SUCCEEDED
    assert canonical.result["source"]["content_id"] == "7412345678901234567"

    short = StageOutcome.model_validate(
        await provider.invoke("source.resolve", {"url": "https://v.douyin.com/iRNBho6G/"})
    )
    assert short.status is StageOutcomeStatus.NEED_HUMAN
    assert short.error_code == "NEEDS_EXPANSION"


async def test_fixture_name_is_allowlisted() -> None:
    provider = _provider()
    try:
        await provider.invoke(
            "source.discover",
            {"query": "ai", "fixture": "../../settings.env"},
        )
    except ValueError as exc:
        assert "allowlist" in str(exc)
    else:
        raise AssertionError("路径穿越 fixture 应被拒绝")


class _UploadRecorder:
    def __init__(self) -> None:
        self.data = b""
        self.put_url = ""

    async def stage_ingest_artifact(self, job_id: str) -> dict:
        assert job_id == "job-acquire"
        return {
            "upload_id": "upload-1",
            "put_url": "https://minio.invalid/staging/upload-1?signature=canary",
        }

    async def put_presigned(self, put_url: str, data: bytes, *, mime_type: str) -> None:
        self.put_url = put_url
        self.data = data
        assert mime_type == "video/mp4"

    async def commit_ingest_artifact(
        self,
        job_id: str,
        upload_id: str,
        *,
        filename: str,
        mime_type: str,
        sha256: str,
        size_bytes: int,
    ) -> dict:
        assert upload_id == "upload-1"
        assert filename == "synthetic-source.mp4"
        assert sha256 == hashlib.sha256(self.data).hexdigest()
        assert size_bytes == len(self.data)
        return {
            "id": "artifact-1",
            "sha256": sha256,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
            "media": {
                "duration_s": 1.0,
                "fps": 1.0,
                "width": 16,
                "height": 16,
                "codec": "h264",
            },
        }


async def test_synthetic_acquisition_uploads_and_returns_golden_metrics(
    tmp_path: Path,
) -> None:
    uploads = _UploadRecorder()
    provider = DouyinIngestProvider(
        fixture_dir=FIXTURES,
        upload_client=uploads,
    )
    outcome = StageOutcome.model_validate(
        await provider.invoke(
            "source.acquire",
            {
                "job_id": "job-acquire",
                "source_asset_id": "source-1",
                "fixture": "synthetic_mp4",
            },
        )
    )
    assert outcome.status is StageOutcomeStatus.SUCCEEDED
    assert outcome.result["artifact_id"] == "artifact-1"
    assert "signature=canary" not in outcome.model_dump_json()
    assert len(uploads.data) == 1546
    normal_bytes = uploads.data
    forced = StageOutcome.model_validate(
        await provider.invoke(
            "source.acquire",
            {
                "job_id": "job-acquire",
                "source_asset_id": "source-1",
                "fixture": "synthetic_mp4",
                "force": True,
            },
        )
    )
    assert forced.result["sha256"] != outcome.result["sha256"]
    assert uploads.data.startswith(normal_bytes)

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        pytest.skip("Golden 媒体指标验证需要 ffprobe")
    media_path = tmp_path / "synthetic.mp4"
    media_path.write_bytes(uploads.data)
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(probe.stdout)
    video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
    assert float(data["format"]["duration"]) == pytest.approx(1.0, abs=0.01)
    assert (video["width"], video["height"]) == (16, 16)
    assert video["nb_frames"] == "1"


async def test_acquisition_without_upload_client_is_explicitly_unconfigured() -> None:
    outcome = StageOutcome.model_validate(
        await _provider().invoke(
            "source.acquire",
            {"job_id": "job-1", "fixture": "synthetic_mp4"},
        )
    )
    assert outcome.status is StageOutcomeStatus.NEED_HUMAN
    assert outcome.error_code == "UNCONFIGURED"
