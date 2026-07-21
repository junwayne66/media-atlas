# AGENTS.md

Coder Agent 在本仓库工作的强制规则（依据 docs/implementation/52-repo-structure.md §5）：

1. 按 [docs/implementation/53-coder-agent-roadmap.md](docs/implementation/53-coder-agent-roadmap.md) 的依赖顺序执行；每个 PR/提交只完成一个 Task ID，使用其 §9 的 PR 模板。
2. 新增外部工具、镜像或模型，先更新 [third_party_manifest.yaml](third_party_manifest.yaml)（含许可证与隔离等级）。
3. 新增 Provider 必须包含 descriptor、契约测试、错误映射和健康检查。
4. 新增长流程必须有 Temporal time-skipping test。
5. 新媒体算法必须有合成 Fixture 和 Golden 指标（比较帧/音频/时长，不只比较文件 hash）。
6. 不在测试中使用真实平台账号或生产 Secret；连接器单测只用录制/脱敏 Fixture。
7. 业务模块不得执行任意 shell 字符串；FFmpeg 用参数数组 + 路径白名单。
8. 领域规则：`domain` 包不 import 框架；跨模块只传 ID 和结构化合同；原始事实不可变，修改以新版本保存。
9. 遇到 [53 §10 的停止条件](docs/implementation/53-coder-agent-roadmap.md)（真实账号/付费凭据、许可证不明、验证码/风控、改核心 ADR、Golden 回退）时停止扩大范围，保留 Fake/Manual Adapter 并输出阻塞证据与最小决策问题。

架构与工程约定的完整索引见 [CLAUDE.md](CLAUDE.md)。
