# Quickstart / Acceptance: 本地安全设置

所有示例只使用合成秘密，禁止填真实账号或生产 Key。

## 1. 启动与迁移

```bash
docker compose up -d --build
uv run alembic upgrade head
curl -fsS http://127.0.0.1:8000/healthz
```

打开 `http://127.0.0.1:8080/settings`。首次应显示“凭据库未初始化”。

## 2. 初始化与 Provider

1. 用测试口令初始化凭据库。
2. 分别保存 LLM、ASR、VLM 元数据；为其中一个填入唯一合成 API Key。
3. 刷新页面：非敏感字段保留，API Key 输入为空，仅显示“凭据已保存”。
4. 锁定保险库：非敏感配置可读/可改；替换和清除秘密按钮不可用。
5. 重启 API 容器：保险库状态必须回到 LOCKED。

## 3. 平台账号边界

1. 创建 DOUYIN + OFFICIAL_API + SERVER_ENCRYPTED 账号，保存合成 Token；状态必须为 UNVERIFIED。
2. 创建 TIKTOK + BROWSER_AUTOMATION + DESKTOP 账号时只能填 Keychain handle；Web 表单不得出现 Cookie 输入。
3. 尝试把 `cookie`、`password` 或 Android 会话字段 POST 到设置 API，必须得到脱敏 422，响应不得出现其值。
4. 页面不得提供真实连接、OAuth、验证码或发布按钮。

## 4. 零泄露检查

使用唯一测试串 `VF_SECRET_CANARY_...`：

```bash
uv run pytest apps/api/tests/test_credential_vault.py \
  apps/api/tests/test_secure_settings_api.py \
  apps/api/tests/test_secure_settings_integration.py
```

自动化测试应检查：

- 原始数据库行只有密文、nonce、tag、KDF 参数和非敏感元数据。
- 所有 GET/错误响应不含 canary。
- 捕获日志不含 canary。
- 删除 owner 后对应服务端密文行不存在。
- 错误口令、锁定状态和过期版本均原子拒绝。

浏览器手工检查：

- URL、localStorage、sessionStorage、console、Network response 无 canary。
- 所有 password 输入在成功、失败、锁定、切换 tab 和刷新后为空。
- 390px 宽视口无横向裁切；tabs 可用键盘左右键切换。

## 5. 全量验证

```bash
uv run ruff check .
uv run pytest
pnpm --filter @videoforge/console typecheck
pnpm --filter @videoforge/console build
make smoke
```

## Known limitations

- 保险库解锁状态只属于当前 API 进程；多 worker 部署必须逐进程解锁，当前 Compose 保持单 worker。
- loopback 仅实现本机单用户边界；远程部署前必须新增 TLS、鉴权与授权。
- 本任务不在线验证 Provider 或平台账号，所有账号始终 UNVERIFIED。
