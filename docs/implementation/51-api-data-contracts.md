# API 与数据合同

## 1. API 约定

- Base：`/v1`。
- JSON 使用 `snake_case`；时间为 RFC3339 UTC；时长统一毫秒。
- ID 不包含业务含义。
- 长操作返回 `202 Accepted` + `operation_id`。
- 写操作支持 `Idempotency-Key`。
- 乐观并发：版本化对象更新带 `If-Match: version`。
- 列表采用 cursor pagination。
- Error 使用统一 `problem+json`。

## 2. Error Contract

```json
{
  "type": "https://videoforge.dev/problems/provider-timeout",
  "title": "Provider timeout",
  "status": 503,
  "code": "PROVIDER_TIMEOUT",
  "detail": "TTS provider did not respond within 60s",
  "retryable": true,
  "correlation_id": "cor_...",
  "context": {"provider": "tts_x", "attempt": 2}
}
```

禁止把栈、Cookie、Token、完整外部响应返回给客户端。

## 3. Project API

### `POST /v1/projects`

```json
{
  "title": "AI 芯片热点解释",
  "creation_mode": "STRUCTURE_REWRITE",
  "trend_cluster_id": "trc_...",
  "source_asset_ids": ["src_..."],
  "source_language": "zh-CN",
  "target_languages": ["zh-CN", "en-US"],
  "platform_targets": ["douyin", "tiktok"],
  "channel_profile_id": "chn_...",
  "template_version_id": "tplv_...",
  "execution_policy": "LOCAL_PREFERRED"
}
```

响应 `201` 返回 Project；若 `start=true`，另返回 Workflow Operation。

### `POST /v1/projects/{id}:start`

可选：

```json
{"from_stage": "INGEST", "until_stage": "REVIEW", "reuse_cache": true}
```

## 4. Source Import API

```http
POST /v1/sources:resolve
POST /v1/sources:import-url
POST /v1/sources:complete-upload
GET  /v1/sources/{id}
GET  /v1/sources/{id}/artifacts
```

`import-url` 只保存 URL/意图并启动 Workflow，API 进程不直接下载大文件。

## 5. Version Update API

```http
POST /v1/projects/{id}/scripts/{version}:fork
PATCH /v1/projects/{id}/scripts/{version}
POST /v1/projects/{id}/timelines/{version}:compile
POST /v1/projects/{id}/variants/{id}:rerun
```

局部重跑 Request：

```json
{
  "scope": {"sentence_ids": ["sen_12"], "text_track_ids": []},
  "stages": ["TTS", "ALIGN", "CAPTION", "RENDER"],
  "provider_overrides": {"tts": "provider_b"}
}
```

服务端验证依赖闭包，不能由客户端漏掉必需下游阶段。

## 6. CreativeTimeline（精简合同）

```json
{
  "schema_version": "1.0",
  "timeline_id": "tl_...",
  "version": 4,
  "fps": {"num": 30, "den": 1},
  "canvas": {"width": 1080, "height": 1920},
  "duration_frames": 1350,
  "tracks": [{
    "id": "v1",
    "kind": "video",
    "segments": [{
      "id": "seg_1",
      "source_artifact_id": "art_1",
      "source_range": {"start_frame": 300, "duration_frames": 120},
      "timeline_range": {"start_frame": 0, "duration_frames": 120},
      "semantic_role": "HOOK",
      "script_sentence_ids": ["sen_1"],
      "transform": {"crop": [0.1, 0, 0.8, 1], "scale": 1.0},
      "effects": [],
      "provenance_ref": "prov_1"
    }]
  }],
  "markers": [{"frame": 0, "kind": "claim", "ref_id": "claim_1"}]
}
```

所有帧换算由 `RationalTime` 工具完成，不在 UI 重复实现。

## 7. Task Envelope

```json
{
  "task_id": "tsk_...",
  "lease_id": "lea_...",
  "task_type": "media.render.ffmpeg",
  "schema_version": "1.0",
  "required_capabilities": ["ffmpeg>=7", "h264_encoder"],
  "inputs": [{
    "artifact_id": "art_...",
    "digest": "sha256:...",
    "download_url": "https://...signed..."
  }],
  "config": {"render_manifest_artifact_id": "art_manifest"},
  "outputs": [{"name": "video", "mime": "video/mp4"}],
  "resources": {"timeout_seconds": 1800, "max_disk_mb": 10000},
  "trace_context": {"traceparent": "..."}
}
```

Worker Completion：

```json
{
  "lease_id": "lea_...",
  "status": "SUCCEEDED",
  "outputs": [{"name": "video", "artifact_id": "art_out", "digest": "sha256:..."}],
  "metrics": {"wall_ms": 33120, "cpu_ms": 80200},
  "tool_versions": {"ffmpeg": "..."}
}
```

## 8. Worker Capability

```json
{
  "worker_id": "wrk_mac_1",
  "os": {"name": "macos", "arch": "arm64", "version": "..."},
  "resources": {"cpu_cores": 10, "memory_mb": 32768, "free_disk_mb": 120000},
  "capabilities": [
    {"name": "ffmpeg", "version": "7.x", "features": ["videotoolbox"]},
    {"name": "asr.whisper_cpp", "models": ["small", "medium"]},
    {"name": "ocr.paddle", "languages": ["zh", "en"]},
    {"name": "render.remotion", "version": "pinned"}
  ],
  "credential_handles": ["cred_tiktok_browser_1"]
}
```

## 9. Provider Interface（Python）

```python
class Provider(Protocol):
    descriptor: ProviderDescriptor

    async def health(self) -> HealthResult: ...

class TTSProvider(Provider, Protocol):
    async def synthesize(self, request: TTSRequest) -> TTSResult: ...

class PublishConnector(Provider, Protocol):
    async def preflight(self, request: PublishRequest) -> PreflightResult: ...
    async def initialize(self, request: PublishRequest) -> UploadSession: ...
    async def upload(self, session: UploadSession, artifact: ArtifactRef) -> UploadResult: ...
    async def submit(self, session: UploadSession) -> SubmitResult: ...
    async def status(self, external_ref: str) -> PublishStatus: ...
```

真实实现不得泄漏外部 SDK 类型到领域层。

## 10. Review API

```http
GET  /v1/review-queue
GET  /v1/projects/{id}/review-bundle
POST /v1/reviews
POST /v1/reviews/{id}/comments
POST /v1/reviews/{id}:invalidate
```

审批 Request 必须包含 `entity_version` 和 `qc_report_ids`；否则不能批准一个已被修改的对象。

## 11. Publish API

```http
POST /v1/publish-jobs
POST /v1/publish-jobs/{id}:schedule
POST /v1/publish-jobs/{id}:cancel
POST /v1/publish-jobs/{id}:retry
POST /v1/publish-jobs/{id}:confirm-human-step
GET  /v1/publish-jobs/{id}
POST /v1/webhooks/{platform}
```

`retry` 对同 Job/幂等键重试；创建副本必须显式 `duplicate=true`。

## 12. Connector Error Mapping

所有外部错误映射到：

```text
AUTH_EXPIRED, AUTH_SCOPE_MISSING, APP_REVIEW_REQUIRED
RATE_LIMITED, PLATFORM_TEMPORARY, PLATFORM_REJECTED
MEDIA_INVALID, ACCOUNT_MISMATCH, CHALLENGE_REQUIRED
SELECTOR_CHANGED, DEVICE_OFFLINE, RESULT_UNKNOWN
```

保留脱敏原始响应 Artifact 供诊断。

## 13. Webhook

- 验签、时间窗、nonce/replay 防护。
- 原始 Body 不可变保存。
- 用 `platform_event_id` 去重。
- 先快速 `2xx`，后续通过 Workflow Signal 处理。
- 未知 PublishJob 的事件进入隔离队列，不自动创建外部帖子记录。

