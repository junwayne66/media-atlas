# Data Model: 可恢复的采集 Worker

## 1. SourceAsset（扩展现有聚合）

新增字段均有默认值，旧 payload 可继续解析：

- `public_metadata`: 作者、标题、描述、封面、时长、发布时间、公开统计、脱敏原始元数据。
- `rights_basis`: UNKNOWN / OWNED / LICENSED / USER_PROVIDED / INTERNAL_APPROVED。
- `rights_attestation_ids[]`: 不可变权利声明 ID。
- `artifact_ids[]`: 已验证的原始媒体 Artifact ID；只追加。
- `discovered_at`, `last_seen_at`: 首次与最近公开观测。

身份继续使用 `platform + content_id`，没有 content id 时用 `sha256(original_input)`。

## 2. ingest_jobs（业务查询投影，不是队列）

| 字段 | 约束/语义 |
|---|---|
| id | 36 字符不透明 ID，PK |
| version | 乐观锁，起始 1 |
| job_type | DISCOVERY_SEARCH / CONTENT_RESOLVE / MEDIA_ACQUIRE / SESSION_CHECK |
| status | PENDING / RUNNING / RETRY_WAIT / NEED_HUMAN / SUCCEEDED / FAILED / CANCELLED |
| platform | 首版固定 douyin |
| idempotency_key | 唯一 |
| workflow_id | Temporal workflow id，唯一可空 |
| worker_task_id | 最近一次 Lease task id，可空 |
| source_asset_id | resolve/acquire 对应来源，可空 |
| discovery_query_id | discovery 对应查询，可空 |
| profile_id | Source Profile，可空 |
| attempt/max_attempts | 业务展示投影 |
| result | 脱敏结构化结果 |
| error_code/error_message | 稳定错误与安全文案 |
| created/started/finished/updated | UTC timestamptz |

禁止在 payload/result/error_message 保存 Cookie、Authorization、口令或预签名 URL。

## 3. ingest_job_events（append-only）

`id`, `job_id`, `event_type`, `from_status`, `to_status`, `actor_id`, `message`,
`details`, `created_at`。无 update/delete repository；确定性 event id 保证 Activity 重放不
重复追加。

## 4. discovery_queries

保存 `platform`, `query_text`, `filters`, `max_items`, `max_scrolls`, `idle_rounds`,
`time_budget_s`, `profile_id`, `created_by`, `created_at`。

## 5. rights_attestations（append-only）

保存 `id`, `source_asset_id`, `basis`, `note`, `actor_id`, `created_at`。UNKNOWN 可作为
来源默认值，但不能创建 MEDIA_ACQUIRE attestation/job。

## 6. source_profiles

保存 `platform`, `profile_key`, `display_name`, `credential_handle`, `status`,
`last_verified_at`, `last_challenge_at`, `metadata` 和乐观锁版本。`credential_handle` 只作
Desktop Broker 字典键，不允许作为路径解释。

## 7. Artifact

继续使用现有不可变 `artifacts`，`kind=source_video`，保留 SHA、size、MIME、媒体技术属性、
工具版本和 S3 引用。普通重复获取复用 SourceAsset 已关联 Artifact；`force=true` 创建新版本。

## 8. 状态转换

```text
PENDING -> RUNNING
RUNNING -> SUCCEEDED | RETRY_WAIT | NEED_HUMAN | FAILED | CANCELLED
RETRY_WAIT -> RUNNING | FAILED | CANCELLED
NEED_HUMAN -> PENDING | CANCELLED
PENDING -> CANCELLED
```

任何其他转换返回冲突。终态不可被旧租约覆盖；每次有效转换与业务变更同事务追加事件。
