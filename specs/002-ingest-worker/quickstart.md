# Quickstart: 可恢复的采集 Worker

## 启动本地全栈

```bash
docker compose up --build -d postgres redis minio temporal temporal-ui migrate api workflow-worker edge-agent console
```

服务地址：Console `http://127.0.0.1:8080`，API `http://127.0.0.1:8000`，
Temporal UI `http://127.0.0.1:8233`，MinIO `http://127.0.0.1:9001`。

## 创建离线发现任务

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/ingest/discovery \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-discovery-1' \
  -d '{"platform":"douyin","query":"ai","fixture":"board"}'
```

用响应中的 job id 查询：

```bash
curl -sS http://127.0.0.1:8000/v1/ingest/jobs/JOB_ID
curl -sS http://127.0.0.1:8000/v1/ingest/jobs/JOB_ID/events
```

## 解析规范链接

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/ingest/resolve \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-resolve-1' \
  -d '{"url":"https://www.douyin.com/video/7412345678901234567"}'
```

短链在未配置实时展开时进入人工处置，不会触网。

## 授权后获取合成媒体

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/ingest/sources/SOURCE_ID/acquisitions \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-acquire-1' \
  -d '{"rights_basis":"OWNED","rights_note":"本地合成验收素材"}'
```

UNKNOWN 会在创建 job 前返回 409，MinIO 不产生对象。

结构化就绪诊断：

```bash
curl -sS http://127.0.0.1:8000/v1/ingest/readiness
```

## 人工恢复与取消

挑战 Fixture 创建的任务进入 NEED_HUMAN 后可调用：

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/ingest/jobs/JOB_ID/resume
curl -sS -X POST http://127.0.0.1:8000/v1/ingest/jobs/JOB_ID/cancel
```

真实验证码与风控必须在受控浏览器外部人工处理，本实现不提供绕过能力。

## 验证

```bash
uv run pytest packages/contracts-py/tests packages/provider-sdk/tests \
  connectors/sources/douyin/tests packages/persistence/tests \
  packages/workflows/tests services/edge-agent/tests apps/api/tests
```
