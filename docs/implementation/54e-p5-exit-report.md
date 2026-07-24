# P5 Exit 验收报告（审核与发布）

对照 `docs/implementation/53` §7 的 P5 Exit（**测试账号端到端发布；网络超时重试不重复发；
挑战必停给人工**）+ `docs/modules/44 §13` 相关条目，用 VF-501..507 的 domain + Fake
adapter 在 `tests/acceptance/` 跑通发布闭环。

跑法：`uv run pytest tests/acceptance/test_p5_exit_*.py -q`（并入 pytest `testpaths`，
`make test` 强制执行）。**全程 Fake-first，不触真实平台。**

## 覆盖

### ① 测试账号端到端发布 —— ✅（Fake-first）
`test_p5_exit_publish_flow.py`：`p5_flow.run_publish` 串起 VF-502 预检 + VF-503/504
executor 生命周期——预检 `publishable` → 建 Job → `submit` → `query_status` →
`confirm_success` → **SUCCEEDED + 保存 external_post_id**，护栏 `validate_publish_job` 空。
**四个 Fake adapter（TikTok/抖音/浏览器/Android）各跑通**。非空跑护栏：未授权 / 账号封禁 /
媒体不符 → 预检 `publishable=False`，绝不进入发布。

### ② 网络超时重试不重复发 —— ✅
`test_p5_exit_idempotency.py`：提交后网络超时（未知）→ `reconcile_publish` 先查状态，匹配到
已存在外部帖子 → **SUCCEEDED_RECONCILED，绝不盲目重发**（只有一次真实提交 token）；盲目二次
`record_submission` 被 `IllegalPublishTransition` 硬拦——**即使经"等人工 → 恢复回 UPLOADING"
回路，durable token latch 仍拒重发**；未查到 → VERIFYING 继续查、不重发；executor 层按
idempotency_key 幂等（同 Job 重试返回同一帖子 + `idempotent_replay`）；护栏保证永不出现两个
外部 post token（DOUBLE_SUBMIT）。

### ③ 挑战必停给人工，绝不盲点 —— ✅
`test_p5_exit_challenge.py`：浏览器（登录失效/验证码/设备确认/内容警告/风控 信号）、真机
（设备确认 / 就绪门未过）、官方 API（challenge / auth_required）——一律 CHALLENGE 或
AUTH_REQUIRED、**external_post_id 为 None（没有绕过去发布）**，Job 仍在 UPLOADING 可安全转
`WAITING_FOR_HUMAN`。浏览器非白名单域名直接 FAILED 拒发。挑战分类：每种信号判为阻塞，正常页
不阻塞。

### ④ 任一版本修改使旧审批失效 —— ✅（§13）
`test_p5_exit_review_account.py`：VF-501 审批绑定确切 版本+内容+实体——改版本（重渲染）/ 改
内容（改文案）/ 换实体，`is_approval_valid` 全部失效；未改 → 有效。

### ⑤ 发布前后确认账号 —— ✅（§13）
同上：VF-502 预检授权/账号状态 + VF-506 真机前台账号红线——前台账号 ≠ 目标 →
`WRONG_FOREGROUND_ACCOUNT`，绝不发到错号。

## 诚实登记（延后 / stop-condition）

- **真实测试账号端到端发布**：需真实平台账号 + 应用审核 + 凭据 → **stop-condition**。本关口用
  Fake adapter 跑通状态机与幂等/挑战/账号语义；真实 Direct Post/Creator Info/上传/Webhook 的
  live 调用未接入（Unconfigured executor 返回 UNCONFIGURED）。
- **真实网络超时/风控**：Fake 注入模拟；真实平台的超时/风控行为待接入真实平台。
- **1/3/6/24/72h 指标快照**（§10）属 **P6 效果反馈**（VF-601 起），不在 P5。

## 结论

P5 Exit 三条核心（端到端发布 / 重试不重复发 / 挑战必停）+ §13 的审批失效与账号确认，在
**判定/状态机/幂等/安全语义层面全部 Fake-first 跑通并非空验证**；真实平台 live 集成诚实标注为
stop-condition。跑 `tests/acceptance/test_p5_exit_*.py` → 17 passed；全 acceptance → 72
passed；全套（contracts + domain + provider-sdk + acceptance）→ **1240 passed**；lint 全绿；
schema 零 drift。

**P5 审核与发布 CLOSED**（骨架/判定/幂等/安全层面；真实平台官方 API/浏览器/真机 live 驱动随
真实账号 + 应用审核 + 凭据接入时补齐）。下一阶段：**P6 效果反馈**（VF-601 Metrics Connectors
起——§10 指标快照 + null 语义、§11 归因与学习信号；非发布类 Fake-first 可做，真实平台数据 API
回采属 stop-condition）。
