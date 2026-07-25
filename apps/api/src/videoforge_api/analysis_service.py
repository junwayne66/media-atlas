"""分析链应用服务（补齐 P2 遗留的 AnalysisWorkflow 落地面）。

四阶段：ASR → OCR/文本轨 → 代表帧 + VLM → Blueprint 融合。每阶段：

1. **输入摘要**：ASR 阶段用素材的 `file_sha256`（**没有本地文件的素材直接 409**——诚实拒绝，
   绝不假装分析）；下游阶段用上游产物 canonical JSON 的 sha256，形成「改上游 → 下游全重算」链。
2. **缓存键** = VF-201 `activity_cache_key`(input_digest, provider, tool_version, 规范化 config,
   schema_version)。
3. 按 (kind, cache_key) 命中即复用产物、**不再调 Provider**（41 §11）；未命中才调 Fake Provider，
   产物过 domain 后处理/护栏再落库。

**全程 Fake（无真实引擎、无网络）**：provider 名如实写成 `fake-asr` 等，UI 一眼能看出是 Fake。
真实 ASR/OCR/VLM/LLM 引擎 + 权重仍是停止条件（53 §10）。

api 是组合层：这里允许同时用 persistence + domain + provider-sdk + media-core。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from videoforge_api.demo_recordings import (
    DEMO_LANGUAGES,
    load_ocr_provider,
    load_transcripts,
    load_vlm_provider,
)
from videoforge_contracts import (
    SourceAsset,
    TextTrackSet,
    Transcript,
    VideoBlueprint,
    VisualAnalysis,
)
from videoforge_contracts.ids import new_id
from videoforge_domain.blueprint import (
    build_candidate_rhetorical_beats,
    build_visual_beats,
    validate_blueprint,
)
from videoforge_domain.frame_sampling import select_representative_frames
from videoforge_domain.texttrack import track_text_observations
from videoforge_domain.transcript import mark_low_confidence
from videoforge_media_core.job_manifest import activity_cache_key
from videoforge_persistence import (
    AnalysisArtifactRecord,
    AnalysisArtifactRepository,
    AnalysisRunRecord,
    AnalysisRunRepository,
    NotFoundError,
    ProjectRepository,
    SourceAssetRepository,
    record_event,
    session_scope,
)
from videoforge_provider_sdk.asr import ASRRequest
from videoforge_provider_sdk.blueprint_fusion import (
    BlueprintFusionRequest,
    FakeBlueprintFusionProvider,
)
from videoforge_provider_sdk.ocr import OCRRequest
from videoforge_provider_sdk.vlm import VLMRequest

# 产物 kind ↔ 合同
ARTIFACT_KINDS = ("transcript", "text_track_set", "visual_analysis", "video_blueprint")

_ASR_PROVIDER = "fake-asr"
_OCR_PROVIDER = "fake-ocr"
_VLM_PROVIDER = "fake-vlm"
_FUSION_PROVIDER = "fake-blueprint-fusion"
_TOOL_VERSION = "1"

_MAX_FRAMES = 40
_PERIODIC_INTERVAL_MS = 5000


class SourceNotAnalyzable(Exception):
    """素材尚无本地文件（MANUAL_FALLBACK / NEEDS_EXPANSION / UNRESOLVABLE）→ 409。"""


class UnsupportedAnalysisLanguage(Exception):
    """没有该语言的 Fake 录制（真实引擎属停止条件）→ 422。"""


def canonical_digest(payload: dict[str, Any]) -> str:
    """产物 canonical JSON 的 sha256——下游阶段的输入摘要，形成重算链。"""
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class _StageOutcome:
    kind: str
    cache_key: str
    cache_hit: bool
    artifact_id: str
    payload: dict[str, Any]
    provider: str

    def as_stage(self) -> dict[str, Any]:
        return {
            "stage": self.kind,
            "status": "COMPLETED",
            "cache_key": self.cache_key,
            "cache_hit": self.cache_hit,
            "artifact_id": self.artifact_id,
            "provider": self.provider,
        }


class AnalysisService:
    """组合 persistence + domain + provider-sdk 的分析链执行器。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # —— 执行 ——

    def run(self, project_id: str, source_asset_id: str, language: str) -> AnalysisRunRecord:
        if language not in DEMO_LANGUAGES:
            raise UnsupportedAnalysisLanguage(
                f"无 {language} 的 Fake 录制（可用：{sorted(DEMO_LANGUAGES)}）；"
                "真实 ASR/OCR/VLM 引擎接入属停止条件"
            )
        with session_scope(self._engine) as s:
            ProjectRepository(s).get(project_id)  # 不存在 → NotFoundError → 404
            asset = SourceAssetRepository(s).get(source_asset_id)
            self._require_local_media(asset)

            now = datetime.now(UTC)
            run_id = new_id()
            stages: list[dict[str, Any]] = []
            artifacts = AnalysisArtifactRepository(s)

            try:
                transcript_stage = self._stage_transcript(
                    artifacts, project_id, asset, language, now
                )
                stages.append(transcript_stage.as_stage())
                transcript = Transcript.model_validate(transcript_stage.payload)

                tracks_stage = self._stage_text_tracks(
                    artifacts, project_id, transcript_stage, transcript, language, now
                )
                stages.append(tracks_stage.as_stage())
                track_set = TextTrackSet.model_validate(tracks_stage.payload)

                visual_stage = self._stage_visual(
                    artifacts, project_id, tracks_stage, transcript, track_set, language, now
                )
                stages.append(visual_stage.as_stage())
                visual = VisualAnalysis.model_validate(visual_stage.payload)

                blueprint_stage = self._stage_blueprint(
                    artifacts, project_id, visual_stage, transcript, track_set, visual, now
                )
                stages.append(blueprint_stage.as_stage())
            except _BlueprintInvalid as exc:
                stages.append(exc.stage)
                run = AnalysisRunRecord(
                    id=run_id,
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    language=language,
                    status="FAILED",
                    stages=stages,
                    created_at=now,
                    updated_at=now,
                )
                AnalysisRunRepository(s).create(run)
                return run

            run = AnalysisRunRecord(
                id=run_id,
                project_id=project_id,
                source_asset_id=source_asset_id,
                language=language,
                status="COMPLETED",
                stages=stages,
                created_at=now,
                updated_at=now,
            )
            AnalysisRunRepository(s).create(run)
            record_event(
                s,
                aggregate_type="analysis_run",
                aggregate_id=run.id,
                event_type="analysis.completed",
                payload={
                    "run_id": run.id,
                    "project_id": project_id,
                    "source_asset_id": source_asset_id,
                    "language": language,
                    "stages": stages,
                },
            )
            return run

    # —— 查询 ——

    def latest_run(self, project_id: str) -> AnalysisRunRecord:
        with session_scope(self._engine) as s:
            return AnalysisRunRepository(s).latest_for_project(project_id)

    def latest_artifact(self, project_id: str, kind: str) -> dict[str, Any]:
        with session_scope(self._engine) as s:
            run = AnalysisRunRepository(s).latest_for_project(project_id)
            for stage in run.stages:
                if stage.get("stage") == kind and stage.get("artifact_id"):
                    return AnalysisArtifactRepository(s).get(stage["artifact_id"]).payload
            raise NotFoundError("analysis_artifact", f"{project_id}/{kind}")

    # —— 阶段实现 ——

    @staticmethod
    def _require_local_media(asset: SourceAsset) -> None:
        if not asset.file_sha256:
            raise SourceNotAnalyzable(
                f"素材 {asset.id} 尚无本地文件（当前处置 {asset.disposition}）；"
                "请先人工下载原片并用 /v1/sources/import-file 关联后再分析"
            )

    def _cached_or_compute(
        self,
        artifacts: AnalysisArtifactRepository,
        *,
        project_id: str,
        kind: str,
        input_digest: str,
        provider: str,
        config: dict[str, Any],
        created_at: datetime,
        compute,  # noqa: ANN001 - 局部回调，返回 payload dict
    ) -> _StageOutcome:
        cache_key = activity_cache_key(
            input_digest=input_digest,
            provider=provider,
            tool_version=_TOOL_VERSION,
            config=config,
        )
        cached = artifacts.find_cached(kind, cache_key)
        if cached is not None:
            return _StageOutcome(
                kind=kind,
                cache_key=cache_key,
                cache_hit=True,
                artifact_id=cached.id,
                payload=cached.payload,
                provider=cached.provider,
            )
        payload = compute(cache_key)
        record = AnalysisArtifactRecord(
            id=new_id(),
            project_id=project_id,
            kind=kind,
            cache_key=cache_key,
            payload=payload,
            provider=provider,
            tool_version=_TOOL_VERSION,
            created_at=created_at,
        )
        artifacts.add(record)
        return _StageOutcome(
            kind=kind,
            cache_key=cache_key,
            cache_hit=False,
            artifact_id=record.id,
            payload=payload,
            provider=provider,
        )

    def _stage_transcript(
        self,
        artifacts: AnalysisArtifactRepository,
        project_id: str,
        asset: SourceAsset,
        language: str,
        now: datetime,
    ) -> _StageOutcome:
        def compute(_cache_key: str) -> dict[str, Any]:
            provider = load_transcripts(language)
            result = provider.transcribe(
                ASRRequest(
                    audio_path=Path(asset.local_path or asset.id),
                    language_hint=language,
                )
            )
            if result.transcript is None:
                raise UnsupportedAnalysisLanguage(
                    f"Fake ASR 未产出 {language} 转录：{result.detail}"
                )
            # domain 后处理：细粒度低置信标记（供审核 UI 跳转）
            marked = mark_low_confidence(result.transcript).model_copy(
                update={"source_artifact_id": asset.id}
            )
            return marked.model_dump(mode="json")

        return self._cached_or_compute(
            artifacts,
            project_id=project_id,
            kind="transcript",
            input_digest=asset.file_sha256 or "",
            provider=_ASR_PROVIDER,
            config={"language": language, "policy": "local_preferred"},
            created_at=now,
            compute=compute,
        )

    def _stage_text_tracks(
        self,
        artifacts: AnalysisArtifactRepository,
        project_id: str,
        upstream: _StageOutcome,
        transcript: Transcript,
        language: str,
        now: datetime,
    ) -> _StageOutcome:
        duration_ms = _duration_of(transcript)

        def compute(cache_key: str) -> dict[str, Any]:
            provider = load_ocr_provider(language)
            result = provider.detect(OCRRequest(video_path=Path(transcript.id)))
            tracks = track_text_observations(result.observations, total_duration_ms=duration_ms)
            track_set = TextTrackSet(
                id=f"tts-{cache_key[:16]}",
                source_artifact_id=transcript.source_artifact_id,
                tracks=tracks,
                ocr_provider=_OCR_PROVIDER,
                ocr_version=_TOOL_VERSION,
                created_at=now,
            )
            return track_set.model_dump(mode="json")

        return self._cached_or_compute(
            artifacts,
            project_id=project_id,
            kind="text_track_set",
            input_digest=canonical_digest(upstream.payload),
            provider=_OCR_PROVIDER,
            config={"language": language},
            created_at=now,
            compute=compute,
        )

    def _stage_visual(
        self,
        artifacts: AnalysisArtifactRepository,
        project_id: str,
        upstream: _StageOutcome,
        transcript: Transcript,
        track_set: TextTrackSet,
        language: str,
        now: datetime,
    ) -> _StageOutcome:
        duration_ms = _duration_of(transcript)

        def compute(cache_key: str) -> dict[str, Any]:
            # 无真实媒体 → 无场景切点（诚实留空），采样理由只会是 KEYFRAME/TEXT_CHANGE/
            # LOW_CONFIDENCE/SPEAKER_CHANGE/PERIODIC
            selected = select_representative_frames(
                analysis_id=f"va-{cache_key[:16]}",
                created_at=now,
                duration_ms=duration_ms,
                scene_cuts=(),
                text_tracks=tuple(track_set.tracks),
                transcript=transcript,
                source_artifact_id=transcript.source_artifact_id,
                max_frames=_MAX_FRAMES,
                periodic_interval_ms=_PERIODIC_INTERVAL_MS,
            )
            provider = load_vlm_provider(language)
            result = provider.analyze(VLMRequest(analysis=selected))  # 整批一次调用
            analysis = result.analysis or selected
            return analysis.model_dump(mode="json")

        return self._cached_or_compute(
            artifacts,
            project_id=project_id,
            kind="visual_analysis",
            input_digest=canonical_digest(upstream.payload),
            provider=_VLM_PROVIDER,
            config={
                "language": language,
                "max_frames": _MAX_FRAMES,
                "periodic_interval_ms": _PERIODIC_INTERVAL_MS,
            },
            created_at=now,
            compute=compute,
        )

    def _stage_blueprint(
        self,
        artifacts: AnalysisArtifactRepository,
        project_id: str,
        upstream: _StageOutcome,
        transcript: Transcript,
        track_set: TextTrackSet,
        visual: VisualAnalysis,
        now: datetime,
    ) -> _StageOutcome:
        duration_ms = _duration_of(transcript)

        def compute(cache_key: str) -> dict[str, Any]:
            candidates = build_candidate_rhetorical_beats(transcript, duration_ms)
            visual_beats = build_visual_beats(visual, duration_ms)
            result = FakeBlueprintFusionProvider().fuse(
                BlueprintFusionRequest(
                    blueprint_id=f"bp-{cache_key[:16]}",
                    created_at=now,
                    duration_ms=duration_ms,
                    candidate_beats=candidates,
                    visual_beats=visual_beats,
                    transcript=transcript,
                    source_artifact_id=transcript.source_artifact_id,
                )
            )
            if result.blueprint is None:
                raise _BlueprintInvalid(
                    {
                        "stage": "video_blueprint",
                        "status": "FAILED",
                        "cache_key": cache_key,
                        "cache_hit": False,
                        "artifact_id": None,
                        "provider": _FUSION_PROVIDER,
                        "error": result.detail or "融合未产出蓝图",
                    }
                )
            issues = _validate(result.blueprint, transcript, track_set)
            if issues:
                # 护栏不通过 → run FAILED，issues 落进 stages（不静默放行不合规蓝图）
                raise _BlueprintInvalid(
                    {
                        "stage": "video_blueprint",
                        "status": "FAILED",
                        "cache_key": cache_key,
                        "cache_hit": False,
                        "artifact_id": None,
                        "provider": _FUSION_PROVIDER,
                        "error": "validate_blueprint 未通过",
                        "issues": issues,
                    }
                )
            return result.blueprint.model_dump(mode="json")

        return self._cached_or_compute(
            artifacts,
            project_id=project_id,
            kind="video_blueprint",
            input_digest=canonical_digest(upstream.payload),
            provider=_FUSION_PROVIDER,
            config={"duration_ms": duration_ms},
            created_at=now,
            compute=compute,
        )


class _BlueprintInvalid(Exception):
    """蓝图护栏未通过：携带要写入 run.stages 的阶段记录。"""

    def __init__(self, stage: dict[str, Any]) -> None:
        super().__init__(stage.get("error", "blueprint invalid"))
        self.stage = stage


def _validate(
    blueprint: VideoBlueprint, transcript: Transcript, track_set: TextTrackSet
) -> list[str]:
    issues = validate_blueprint(
        blueprint,
        transcript_segment_ids={s.id for s in transcript.segments},
        text_track_ids={t.id for t in track_set.tracks},
    )
    return [f"{i.kind}:{i.ref}:{i.detail}" for i in issues]


def _duration_of(transcript: Transcript) -> int:
    if transcript.duration_ms:
        return transcript.duration_ms
    return max((s.end_ms for s in transcript.segments), default=1)


__all__ = [
    "ARTIFACT_KINDS",
    "AnalysisService",
    "SourceNotAnalyzable",
    "UnsupportedAnalysisLanguage",
    "canonical_digest",
]
