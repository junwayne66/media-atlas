"""Edge Agent 上的 Douyin 离线采集 Provider（VF-108）。

首版只回放脱敏 Fixture、执行纯 URL 解析和合成媒体上传；不 import Playwright、不读取
真实 Profile/Cookie，也不发平台网络请求。
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from videoforge_connector_douyin import DouyinDiscoveryConnector, FixtureFetcher
from videoforge_contracts import (
    HealthState,
    StageOutcome,
    StageOutcomeStatus,
)
from videoforge_provider_sdk import (
    DiscoveryMode,
    DiscoveryRequest,
    DiscoveryStatus,
    UnresolvableUrl,
    resolve_url,
)

_ALLOWED_FIXTURES = frozenset(
    {
        "board_response.json",
        "challenge_response.json",
        "drift_response.json",
        "empty_response.json",
        "manual_import.json",
    }
)
_SYNTHETIC_MP4 = base64.b64decode(
    "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAMVbW9vdgAAAGxtdmhkAAAAAAAA"
    "AAAAAAAAAAAD6AAAA+gAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAA"
    "AAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAj90cmFrAAAAXHRr"
    "aGQAAAADAAAAAAAAAAAAAAABAAAAAAAAA+gAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAA"
    "AAAAAAABAAAAAAAAAAAAAAAAAABAAAAAABAAAAAQAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAA"
    "AAEAAAPoAAAAAAABAAAAAAG3bWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAABAAAAAQABVxAAA"
    "AAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABYm1pbmYA"
    "AAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAA"
    "AQAAASJzdGJsAAAAvnN0c2QAAAAAAAAAAQAAAK5hdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAA"
    "AAAAABAAEABIAAAASAAAAAAAAAABFUxhdmM2Mi4yOC4xMDEgbGlieDI2NAAAAAAAAAAAAAAA"
    "GP//AAAANGF2Y0MBZAAK/+EAF2dkAAqs2V7ARAAAAwAEAAADAAg8SJZYAQAGaOvjyyLA/fj4"
    "AAAAABBwYXNwAAAAAQAAAAEAAAAUYnRydAAAAAAAABYoAAAAAAAAABhzdHRzAAAAAAAAAAEA"
    "AAABAABAAAAAABxzdHNjAAAAAAAAAAEAAAABAAAAAQAAAAEAAAAUc3RzegAAAAAAAALFAAAA"
    "AQAAABRzdGNvAAAAAAAAAAEAAANFAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAA"
    "AAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExh"
    "dmY2Mi4xMi4xMDEAAAAIZnJlZQAAAs1tZGF0AAACrQYF//+p3EXpvebZSLeWLNgg2SPu73gy"
    "NjQgLSBjb3JlIDE2NSByMzIyMiBiMzU2MDVhIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAt"
    "IENvcHlsZWZ0IDIwMDMtMjAyNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRt"
    "bCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4Mzow"
    "eDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0x"
    "IG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFk"
    "em9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTEg"
    "bG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBp"
    "bnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1l"
    "cz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEg"
    "b3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEgc2NlbmVjdXQ9"
    "NDAgaW50cmFfcmVmcmVzaD0wIHJjX2xvb2thaGVhZD00MCByYz1jcmYgbWJ0cmVlPTEgY3JmPTIz"
    "LjAgcWNvbXA9MC42MCBxcG1pbj0wIHFwbWF4PTY5IHFwc3RlcD00IGlwX3JhdGlvPTEuNDAg"
    "YXE9MToxLjAwAIAAAAAQZYiEABX//vfJ78Cm69vfgQ=="
)


class IngestArtifactClient(Protocol):
    async def stage_ingest_artifact(self, job_id: str) -> dict[str, Any]: ...

    async def put_presigned(
        self, put_url: str, data: bytes, *, mime_type: str
    ) -> None: ...

    async def commit_ingest_artifact(
        self,
        job_id: str,
        upload_id: str,
        *,
        filename: str,
        mime_type: str,
        sha256: str,
        size_bytes: int,
    ) -> dict[str, Any]: ...


def _fixture_root() -> Path:
    import videoforge_connector_douyin

    return Path(videoforge_connector_douyin.__file__).resolve().parents[2] / "fixtures"


class DouyinIngestProvider:
    def __init__(
        self,
        *,
        fixture_dir: Path | None = None,
        upload_client: IngestArtifactClient | None = None,
    ) -> None:
        self._fixture_dir = fixture_dir or _fixture_root()
        self._upload_client = upload_client
        self.descriptor = DouyinDiscoveryConnector().descriptor

    async def health_check(self) -> HealthState:
        # 纯本地检查；不得用 health probe 偷偷访问真实平台。
        return (
            HealthState.HEALTHY
            if (self._fixture_dir / "board_response.json").is_file()
            else HealthState.UNHEALTHY
        )

    async def invoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        if capability == "source.discover":
            return self._discover(payload).model_dump(mode="json")
        if capability in {"source.resolve", "source.metadata"}:
            return self._resolve(payload).model_dump(mode="json")
        if capability == "source.acquire":
            return (await self._acquire(payload)).model_dump(mode="json")
        return StageOutcome(
            status=StageOutcomeStatus.PERMANENT_ERROR,
            error_code="CAPABILITY_UNSUPPORTED",
            message=f"不支持能力: {capability}",
        ).model_dump(mode="json")

    def _load_fixture(self, name: str) -> dict[str, Any]:
        if name not in _ALLOWED_FIXTURES:
            raise ValueError(f"fixture 不在 allowlist: {name}")
        return json.loads((self._fixture_dir / name).read_text(encoding="utf-8"))

    def _discover(self, payload: dict[str, Any]) -> StageOutcome:
        fixture = str(payload.get("fixture") or "board_response.json")
        raw = self._load_fixture(fixture)
        connector = DouyinDiscoveryConnector(fetcher=FixtureFetcher(default=raw))
        result = connector.discover(
            DiscoveryRequest(
                mode=DiscoveryMode.KEYWORD,
                query=str(payload.get("query") or payload.get("topic") or "__fixture__"),
                platform="douyin",
                limit=min(int(payload.get("max_items", 30)), 200),
            )
        )
        if result.status is DiscoveryStatus.OK:
            return StageOutcome(
                status=StageOutcomeStatus.SUCCEEDED,
                result={
                    "platform": "douyin",
                    "fixture": fixture,
                    "snapshots": [
                        item.model_dump(mode="json")
                        for item in result.snapshots[: int(payload.get("max_items", 30))]
                    ],
                    "result_count": min(
                        len(result.snapshots), int(payload.get("max_items", 30))
                    ),
                },
            )
        if result.status is DiscoveryStatus.EMPTY:
            return StageOutcome(
                status=StageOutcomeStatus.EMPTY,
                result={
                    "platform": "douyin",
                    "fixture": fixture,
                    "snapshots": [],
                    "result_count": 0,
                },
            )
        if result.status in {DiscoveryStatus.CHALLENGE, DiscoveryStatus.UNCONFIGURED}:
            return StageOutcome(
                status=StageOutcomeStatus.NEED_HUMAN,
                error_code=str(result.error_code or "UNCONFIGURED"),
                message=result.detail or "需要人工处理",
                result={"platform": "douyin", "fixture": fixture},
            )
        return StageOutcome(
            status=StageOutcomeStatus.PERMANENT_ERROR,
            error_code=str(result.error_code or "RESULT_UNKNOWN"),
            message=result.detail or "采集 Fixture 无法解析",
            result={"platform": "douyin", "fixture": fixture},
        )

    async def _acquire(self, payload: dict[str, Any]) -> StageOutcome:
        if payload.get("fixture") != "synthetic_mp4" or self._upload_client is None:
            return StageOutcome(
                status=StageOutcomeStatus.NEED_HUMAN,
                error_code="UNCONFIGURED",
                message="真实媒体获取未启用；仅允许显式 synthetic_mp4 Fixture",
            )
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            return StageOutcome(
                status=StageOutcomeStatus.PERMANENT_ERROR,
                error_code="JOB_ID_REQUIRED",
                message="合成媒体上传缺少 job_id",
            )
        staged = await self._upload_client.stage_ingest_artifact(job_id)
        put_url = str(staged["put_url"])
        upload_id = str(staged["upload_id"])
        media_bytes = _SYNTHETIC_MP4
        if payload.get("force") is True:
            # MP4 允许末尾附加未知数据；ffprobe 仍会复核媒体流，job 标记让强制版本哈希稳定区分。
            media_bytes += f"videoforge-force:{job_id}".encode()
        sha256 = hashlib.sha256(media_bytes).hexdigest()
        await self._upload_client.put_presigned(
            put_url, media_bytes, mime_type="video/mp4"
        )
        artifact = await self._upload_client.commit_ingest_artifact(
            job_id,
            upload_id,
            filename="synthetic-source.mp4",
            mime_type="video/mp4",
            sha256=sha256,
            size_bytes=len(media_bytes),
        )
        media = artifact.get("media") or {}
        return StageOutcome(
            status=StageOutcomeStatus.SUCCEEDED,
            result={
                "source_asset_id": payload.get("source_asset_id"),
                "artifact_id": artifact["id"],
                "sha256": artifact["sha256"],
                "size_bytes": artifact["size_bytes"],
                "mime_type": artifact["mime_type"],
                "media": {
                    key: media.get(key)
                    for key in ("duration_s", "fps", "width", "height", "codec")
                },
            },
        )

    @staticmethod
    def _resolve(payload: dict[str, Any]) -> StageOutcome:
        raw = str(payload.get("url") or payload.get("input") or "")
        try:
            source = resolve_url(raw)
        except UnresolvableUrl as exc:
            return StageOutcome(
                status=StageOutcomeStatus.PERMANENT_ERROR,
                error_code="UNRESOLVABLE_INPUT",
                message=str(exc),
            )
        if source.platform != "douyin":
            return StageOutcome(
                status=StageOutcomeStatus.PERMANENT_ERROR,
                error_code="PLATFORM_UNSUPPORTED",
                message="VF-108 首版只支持抖音",
            )
        if source.needs_expansion:
            return StageOutcome(
                status=StageOutcomeStatus.NEED_HUMAN,
                error_code="NEEDS_EXPANSION",
                message="短链实时展开未启用；请粘贴规范链接",
                result={"platform": "douyin", "short_url": source.short_url},
            )
        return StageOutcome(
            status=StageOutcomeStatus.SUCCEEDED,
            result={
                "source": {
                    "platform": source.platform,
                    "content_id": source.content_id,
                    "canonical_url": source.canonical_url,
                    "original_input": source.raw_input,
                }
            },
        )


__all__ = ["DouyinIngestProvider", "IngestArtifactClient"]
