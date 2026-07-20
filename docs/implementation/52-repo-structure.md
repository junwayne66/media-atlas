# 推荐代码仓库结构

## 1. Monorepo

```text
videoforge/
├── AGENTS.md
├── README.md
├── compose.yaml
├── pyproject.toml
├── uv.lock
├── pnpm-workspace.yaml
├── package.json
├── rust-toolchain.toml
├── apps/
│   ├── api/                     # FastAPI 启动与路由装配
│   ├── web/                     # Vue 管理台
│   ├── desktop/                 # Tauri + Vue Desktop
│   └── temporal-worker/         # Workflow 与轻 Activity 启动
├── services/
│   ├── edge-agent/              # Python/Rust Sidecar Worker
│   ├── media-worker/            # FFmpeg/OCR/ASR/分析
│   └── gpu-worker/              # 云端可选镜像
├── packages/
│   ├── domain/                  # 纯领域对象/规则，无框架依赖
│   ├── application/             # Use cases/服务/端口
│   ├── persistence/             # SQLAlchemy/Alembic/Outbox
│   ├── workflows/               # Temporal 定义
│   ├── contracts-py/            # Pydantic API/Event/Task Schema
│   ├── contracts-ts/            # 从 OpenAPI/Schema 生成
│   ├── media-core/              # Probe、RationalTime、Artifact
│   ├── timeline/                # CreativeTimeline/OTIO/Validator
│   ├── render-ffmpeg/           # Render Graph Compiler
│   ├── render-remotion/         # React 模板/Player/Renderer
│   ├── qc/                      # QA Gate 和报告
│   ├── provider-sdk/            # Provider/Connector Protocol
│   └── ui-kit/                  # Web/Desktop 共享 UI
├── connectors/
│   ├── sources/
│   │   ├── douyin/
│   │   └── tiktok/
│   ├── downloads/
│   │   ├── ytdlp/
│   │   └── f2/
│   ├── ai/
│   │   ├── asr/
│   │   ├── ocr/
│   │   ├── llm/
│   │   ├── vlm/
│   │   ├── tts/
│   │   └── lipsync/
│   ├── assets/
│   ├── publishing/
│   │   ├── douyin_official/
│   │   ├── tiktok_official/
│   │   ├── browser/
│   │   └── android_device/
│   └── exporters/
│       ├── otio/
│       ├── davinci/
│       └── capcut/
├── templates/
│   ├── channels/
│   ├── creative/
│   ├── captions/
│   └── platform/
├── schemas/                     # JSON Schema 真值
├── migrations/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── workflow/
│   ├── media-golden/
│   ├── connector-canary/
│   └── e2e/
├── fixtures/
│   ├── synthetic-media/
│   ├── connector-responses/
│   └── evaluation-set/
├── infra/
│   ├── docker/
│   ├── temporal/
│   ├── observability/
│   └── macos/
├── scripts/                     # 只放开发/发布脚本，不放业务逻辑
├── docs/
└── third_party_manifest.yaml
```

## 2. 依赖方向

```text
apps -> application -> domain
                 -> provider-sdk
                 -> timeline/media-core
infrastructure/connectors -> application ports
workflows -> application commands
```

- `domain` 不 import FastAPI、SQLAlchemy、Temporal、FFmpeg 或外部 SDK。
- Connector 实现 application 定义的 Port。
- UI 只依赖生成的 contracts-ts 和 API SDK。
- Remotion 包不能反向成为 Timeline 类型定义。

## 3. 模块内部模板

```text
packages/application/trends/
├── commands.py
├── queries.py
├── service.py
├── ports.py
├── events.py
└── policies.py

connectors/sources/tiktok/
├── descriptor.yaml
├── connector.py
├── error_mapping.py
├── fixtures/
├── tests/
└── README.md
```

`descriptor.yaml` 声明能力、版本、限流、许可证和所需 Secret。

## 4. 模板与 Prompt

Prompt 不散落在 Python 字符串：

```text
templates/creative/ai-tech-explainer/v1/
├── template.yaml
├── brief.schema.json
├── prompts/
│   ├── blueprint-system.md
│   ├── script-system.md
│   └── reflection-system.md
├── remotion/
├── qc.yaml
└── evaluation.yaml
```

Template Version 的 digest 包含全部配置、Prompt、Remotion 组件版本和 QC 门槛。

## 5. `AGENTS.md` 建议

项目根应告诉 Coder Agent：

- 按 `implementation/53-coder-agent-roadmap.md` 的依赖顺序执行。
- 每个 PR 只完成一个 Task ID。
- 新增外部工具先更新 `third_party_manifest.yaml`。
- 新增 Provider 必须含 descriptor、契约测试、错误映射和健康检查。
- 新增长流程必须有 Temporal time-skipping test。
- 新媒体算法必须有合成 Fixture 和 Golden 指标。
- 不在测试中使用真实平台账号或生产 Secret。
- 不允许业务模块执行任意 shell 字符串。

## 6. 分支和发布

- Trunk-based，小 PR，Feature Flag 保护未完成 Connector。
- SemVer 管理 Control Plane、Desktop、Task Contract。
- Control Plane 支持当前和前一 Desktop 协议版本。
- Connector 可独立 patch 发布，但 descriptor 版本必须进入 Audit。
- 模板版本与应用版本解耦。

