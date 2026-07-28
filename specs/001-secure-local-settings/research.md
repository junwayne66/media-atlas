# Phase 0 Research: 本地安全设置

## R1. 服务端凭据库

**Decision**: 初始化时生成随机 32 字节 master DEK；使用 Argon2id 从用户口令派生 32 字节 KEK，以 AES-256-GCM 包装 DEK；每条秘密再用 DEK 独立认证加密。

**Rationale**:

- `argon2-cffi` 提供 `hash_secret_raw` 和 RFC 9106 low-memory Argon2id 参数；默认档为 64 MiB、3 passes、4 lanes、32-byte output。
- PyCryptodome 的 AEAD API 支持随机 nonce、associated data、`encrypt_and_digest` / `decrypt_and_verify`，可同时保护机密性、完整性和 owner/purpose 绑定。
- envelope 结构允许以后只重新包装 DEK 来更换口令，不需要逐条重加密秘密。
- 两个库已在 lockfile 中作为间接依赖存在，但仍作为 API 直接依赖和许可证清单项显式登记。

**Implementation profile**:

- KDF: Argon2id v19，salt 16 bytes，time_cost 3，memory_cost 65536 KiB，parallelism 4，output 32 bytes。
- AEAD: AES-256-GCM，wrapped DEK 和每条秘密各用随机 16-byte nonce、16-byte tag。
- AAD: versioned `wrapped master key` 或 `credential id + owner + purpose`，防止密文记录换位。
- 正确口令通过 wrapped DEK 的 GCM tag 验证，不另外持久化口令 verifier。
- 解封后的 DEK 只在当前 API 进程内 `bytearray` 保存，主动锁定时尽力覆盖；重启后自动锁定。

**Alternatives rejected**:

- 明文 `.env`/JSON：会直接违反零明文落盘。
- 仅哈希秘密：后续 Provider 需要可恢复秘密，哈希不可逆。
- 所有秘密统一进 DB：违反既有 Cookie/设备会话归属 ADR。
- 仅用 Desktop Keychain：当前 Web/API 运行在 Docker，Provider 服务端调用无法直接访问 WebView Keychain。
- 直接把口令派生值当长期数据密钥：换口令需重加密全部记录，envelope 结构更适合密钥生命周期管理。

## R2. 平台账号凭据归属

**Decision**: 严格复用 `AccountBinding`：

- `SERVER_ENCRYPTED`: 官方 API/OAuth Token 进入本地 DB vault。
- `DESKTOP`: 浏览器 Cookie 只写 macOS Keychain；API 只登记 `credential_ref`。
- `DEVICE`: Android 会话留在真机；API 只登记 device handle。

**Rationale**: `docs/architecture/30-system-architecture.md` 和 `PlatformAccount` 合同已把 Cookie/设备会话的解封位置定义为 Desktop/Device。偏离将要求修改核心 ADR，属于停止条件。

**UI consequence**: 纯 Web 设置页只允许服务端 Token 输入；DESKTOP/DEVICE 只填写 handle，并引导用户到现有 Desktop Broker/设备完成秘密写入。账号状态始终 `UNVERIFIED`，不提供“测试连接”按钮。

## R3. API 与事务

**Decision**: 设置写接口将非敏感元数据、`credential_action` 和可选秘密作为一次命令处理。

**Rationale**:

- `KEEP/REPLACE/CLEAR` 消除“空输入是保持还是清除”的歧义。
- gateway 在单个 `session_scope` 内更新 owner、创建/替换/删除密文，失败整体回滚。
- `expected_version` 复用项目现有乐观锁语义，冲突返回 409，前端不自动重试。
- GET 只返回 `credential_configured`，不返回密文、秘密或完整 handle。

**Error hygiene**: 对秘密字段的 Pydantic validation errors 去掉 `input`/敏感上下文；凭据操作前端只显示固定状态文案；设置响应加 `Cache-Control: no-store`。

## R4. 本地网络边界

**Decision**: Compose 所有宿主机发布端口改为 `127.0.0.1` 绑定。

**Rationale**: 当前 API 无用户认证，本功能又新增可修改安全设置的端点；本机单用户假设不应同时把控制面、数据库、Redis、MinIO、Temporal 暴露到局域网。

**Limitation**: loopback 不能防止同一主机上的恶意进程；真正远程部署必须另行增加 TLS、身份认证、CSRF/Origin 策略和多租户授权。

## R5. 前端秘密生命周期

**Decision**: 密码/Token 只存在具体表单组件的局部 `ref`；提交完成、失败、取消、锁定和卸载均清空。

**Rationale**: 当前控制台只有选中项目 ID 使用 localStorage。设置功能不引入全局 store、URL query、localStorage/sessionStorage、响应缓存或秘密回填。

**Verification**: typecheck/build 后用浏览器检查 URL、DOM 可见值、localStorage、sessionStorage、Network response 和 console；后端集成测试扫描 raw DB rows、响应和日志。

## Primary references

- argon2-cffi API and RFC 9106 profiles: https://argon2-cffi.readthedocs.io/en/stable/api.html
- argon2-cffi parameter guidance: https://argon2-cffi.readthedocs.io/en/stable/parameters.html
- PyCryptodome AES/GCM API: https://pycryptodome.readthedocs.io/en/latest/src/cipher/aes.html
- PyCryptodome authenticated modes: https://pycryptodome.readthedocs.io/en/v3.23.0/src/cipher/modern.html
- Repository architecture boundary: `docs/architecture/30-system-architecture.md` §10
- Platform account contract: `packages/contracts-py/src/videoforge_contracts/publish_account.py`
