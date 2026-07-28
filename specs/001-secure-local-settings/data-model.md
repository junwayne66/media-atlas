# Data Model: 本地安全设置

## `vault_metadata`

本地单例记录，主键固定为 `local-v1`。

| Field | Type | Rule |
|---|---|---|
| id | varchar(20) | PK |
| kdf_name | varchar(32) | 固定 `argon2id` |
| kdf_parameters | jsonb | version/time/memory/parallelism/hash length |
| salt | bytea | 16-byte random |
| wrapped_key_nonce | bytea | unique random nonce |
| wrapped_master_key | bytea | AES-GCM wrapped random 32-byte DEK |
| wrapped_key_tag | bytea | 16-byte authentication tag |
| created_at / updated_at | timestamptz | UTC |

数据库中没有 passphrase、KEK 或明文 DEK。初始化只允许一次；错误口令无法通过 wrapped DEK 的 GCM tag 校验。

## `encrypted_credentials`

仅保存 `SERVER_ENCRYPTED` 秘密。

| Field | Type | Rule |
|---|---|---|
| id | varchar(36) | UUIDv7-style ID, PK |
| purpose | varchar(80) | provider/account purpose |
| nonce | bytea | 每次加密随机且不复用 |
| ciphertext | bytea | canonical JSON credential bundle ciphertext |
| auth_tag | bytea | 16-byte GCM tag |
| created_at / updated_at | timestamptz | UTC |

AAD 绑定 schema version、id 和 purpose。不存在读取明文的 REST 端点。

## `provider_configurations`

| Field | Type | Rule |
|---|---|---|
| kind | varchar(30) | PK；LLM/ASR/VLM |
| provider_name | varchar(100) | 非空 |
| model_name | varchar(200) | nullable |
| base_url | text | nullable, only http/https |
| enabled | boolean | default false |
| options | jsonb | 只允许非敏感键，大小受限 |
| credential_ref | varchar(36) | nullable, internal encrypted credential ID |
| row_version | integer | optimistic lock, starts at 1 |
| created_at / updated_at | timestamptz | UTC |

API 视图省略 `credential_ref`，仅计算 `credential_configured` 与 `readiness`。

## `platform_account_bindings`

| Field | Type | Rule |
|---|---|---|
| id | varchar(36) | PK |
| platform | varchar(20) | DOUYIN/TIKTOK |
| display_name | varchar(200) | 非空 |
| external_account_id | varchar(200) | 非空 |
| auth_method | varchar(30) | OFFICIAL_API/BROWSER_AUTOMATION/ANDROID_DEVICE/MANUAL_EXPORT |
| binding | varchar(30) | SERVER_ENCRYPTED/DESKTOP/DEVICE |
| credential_ref | varchar(200) | encrypted row ID 或外部 opaque handle |
| locale | varchar(20) | BCP-47-ish |
| publishing_window | varchar(200) | nullable, nonsecret |
| enabled | boolean | default false |
| verification_status | varchar(20) | 固定 UNVERIFIED |
| row_version | integer | optimistic lock |
| created_at / updated_at | timestamptz | UTC |

唯一约束：`(platform, external_account_id)`。组合约束在应用层执行：

- OFFICIAL_API ↔ SERVER_ENCRYPTED
- BROWSER_AUTOMATION ↔ DESKTOP
- ANDROID_DEVICE ↔ DEVICE
- MANUAL_EXPORT 不要求凭据

## State transitions

```text
Vault: UNINITIALIZED -> UNLOCKED -> LOCKED <-> UNLOCKED

Credential action:
KEEP    : reference unchanged
REPLACE : create new ciphertext / accept new external handle, swap reference,
          then delete old server ciphertext in the same transaction
CLEAR   : clear reference and delete old server ciphertext in the same transaction

Account verification:
UNVERIFIED (fixed in this task; no online transition)
```

## Deletion

- Provider/account deletion verifies `expected_version`.
- `SERVER_ENCRYPTED` credential row is deleted in the same DB transaction.
- DESKTOP/DEVICE reference is invalidated by deleting metadata; UI reminds the user that physical Keychain/device cleanup must happen at that storage locus.
