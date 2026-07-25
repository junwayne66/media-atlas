"""发布 API（docs/modules/44 §3/§4/§5）——VF-502..507 的 REST 面。

**全程 Fake-first，无 live network。**

状态机严格走 domain（`PUBLISH_TRANSITIONS` / `can_submit` / `record_submission` /
`reconcile_publish` / `mark_manually_completed`），端点只做"取 Job → 调 executor → 交 domain 迁移
→ 乐观锁写回"。三条红线：

1. **重试绝不重复发布**：`record_submission` 的幂等硬拦是唯一入口；已提交过的 Job 再 submit →
   409（附 domain 的原文说明）。判"已提交"靠 attempts 里的 `external_post_token`——因此仓储
   整存整取 payload、**绝不剥离 attempts**（VF-503 verifier 警告的落地风险）。
2. **对账不重发**：reconcile 只查状态；查到已存在帖子 → SUCCEEDED_RECONCILED，查不到 → 继续
   VERIFYING，**不会触发第二次 submit**。
3. **挑战必停给人工**：executor 返回 CHALLENGE / AUTH_REQUIRED → WAITING_FOR_HUMAN，
   绝不绕过、绝不改用别的方法硬发。

**并发安全**：所有会调用外部执行器的状态变更（submit / reconcile / manual-complete / preflight）
都在**单事务 + 行锁**内完成：`get_for_update` → 读最新 → 域判定 → 外部调用 → 写回 → commit。
乐观锁单独用不够——两个并发请求会各自过完 `can_submit` 再各自调 `executor.submit`（外部副作用
已经发生），只有写回时才发现冲突（verifier 实测 executor 被调 2 次）。

真实平台发布（官方 API / 浏览器 / 真机）仍是 stop-condition：这里注册的是 Fake executor，
`app.state.publish_executors` 可整体替换（集成测试注入 challenge/限流）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from videoforge_contracts import (
    PlatformPublishSpec,
    PreflightReport,
    PublishJob,
    PublishMediaProbe,
    PublishMetadata,
    PublishMethod,
    PublishPlatform,
    PublishState,
    ReviewSeverity,
)
from videoforge_contracts.ids import new_id
from videoforge_domain.publish_job import (
    IllegalPublishTransition,
    assert_transition,
    can_submit,
    mark_manually_completed,
    new_publish_job,
    reconcile_publish,
    record_submission,
    validate_publish_job,
)
from videoforge_domain.publish_preflight import run_preflight
from videoforge_domain.publish_schedule import compute_copy_idempotency_key, next_publish_time
from videoforge_persistence import (
    DuplicateError,
    NotFoundError,
    VersionConflictError,
    session_scope,
)
from videoforge_persistence.publish import PublishJobRepository, StoredPublishJob
from videoforge_provider_sdk.publish_connector import FakePublishConnector, PublishConnector
from videoforge_provider_sdk.publish_executor import (
    FakeDouyinPublishExecutor,
    FakeTikTokPublishExecutor,
    PublishExecStatus,
    PublishExecutor,
)

# 平台规则集（数据化 §3.1/§3.2/§9 约束）。真实平台的完整规则表随官方接入时校准。
DEFAULT_PUBLISH_SPECS: dict[PublishPlatform, PlatformPublishSpec] = {
    PublishPlatform.TIKTOK: PlatformPublishSpec(
        platform=PublishPlatform.TIKTOK,
        allowed_aspect_ratios=["9:16", "1:1", "16:9"],
        min_width=360,
        min_height=360,
        max_width=4096,
        max_height=4096,
        allowed_video_codecs=["h264", "hevc"],
        allowed_audio_codecs=["aac"],
        allowed_containers=["mp4", "mov"],
        max_file_size_bytes=4 * 1024**3,
        min_duration_ms=3_000,
        max_duration_ms=10 * 60 * 1000,
        title_max_len=150,
        description_max_len=2200,
        max_tags=30,
        tag_max_len=100,
        banned_title_chars=["<", ">"],
    ),
    PublishPlatform.DOUYIN: PlatformPublishSpec(
        platform=PublishPlatform.DOUYIN,
        allowed_aspect_ratios=["9:16", "1:1", "16:9"],
        min_width=360,
        min_height=360,
        max_width=4096,
        max_height=4096,
        allowed_video_codecs=["h264", "hevc"],
        allowed_audio_codecs=["aac"],
        allowed_containers=["mp4"],
        max_file_size_bytes=4 * 1024**3,
        min_duration_ms=3_000,
        max_duration_ms=15 * 60 * 1000,
        title_max_len=55,
        description_max_len=1000,
        max_tags=20,
        tag_max_len=50,
        banned_title_chars=["<", ">"],
    ),
}


def default_publish_executors() -> dict[PublishPlatform, PublishExecutor]:
    """默认执行器：Fake（零网络、按 idempotency_key 幂等）。真实平台接入属 stop-condition。"""
    return {
        PublishPlatform.TIKTOK: FakeTikTokPublishExecutor(),
        PublishPlatform.DOUYIN: FakeDouyinPublishExecutor(),
    }


def default_publish_connectors() -> dict[PublishPlatform, PublishConnector]:
    """默认能力上报连接器：Fake（§3「Connector 返回能力，不由 UI 猜」）。"""
    return {
        PublishPlatform.TIKTOK: FakePublishConnector(platform=PublishPlatform.TIKTOK),
        PublishPlatform.DOUYIN: FakePublishConnector(platform=PublishPlatform.DOUYIN),
    }


def metadata_digest_of(metadata: PublishMetadata) -> str:
    """元数据摘要（幂等键的一维）：canonical JSON 的 sha256，字段一改键就变。"""
    payload = metadata.model_dump(mode="json")
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


# —— 请求/响应模型 ——


class PublishJobCreate(BaseModel):
    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    media_digest: str = Field(min_length=1, description="成片摘要（sha256），幂等键的一维")
    metadata: PublishMetadata
    render_manifest_id: str | None = None
    publishing_window: str = Field(default="immediate", min_length=1)
    copy_index: int = Field(default=0, ge=0, description="≥1 才派生新幂等键（有意的副本）")
    method: PublishMethod = PublishMethod.OFFICIAL_API


class PreflightRequest(BaseModel):
    """预检请求：**只传媒体探针**；元数据一律以建任务时入库的 `publish_metadata` 为准。

    为什么不收请求体元数据：

    1. **元数据参与幂等键**（`metadata_digest_of` → `compute_copy_idempotency_key`），任务建好
       之后就**不可变**。若允许 /preflight 传一份并回写，入库元数据就会与 `job.metadata_digest`
       / 幂等键脱钩，破坏 §5「同内容绝不建第二个任务」的去重锚。换元数据 = 建新任务
       （键自然不同），而不是就地改任务。
    2. **`extra="forbid"`**：旧调用方仍带 `metadata` → 422 大声失败。宁可 422，也不静默改用
       另一份输入——「预检端点展示的报告」与「submit 判定的输入」分叉，正是本字段被删掉的原因。
    """

    model_config = ConfigDict(extra="forbid")

    probe: PublishMediaProbe


class PreflightResponse(BaseModel):
    report: PreflightReport
    job: PublishJob


class SubmitResponse(BaseModel):
    job: PublishJob
    executor_status: str
    idempotent_replay: bool = False
    detail: str | None = None


class ReconcileResponse(BaseModel):
    job: PublishJob
    found_post: bool
    attempts_count: int = Field(description="对账不新增 attempt——此数应与对账前一致")


class ManualCompleteRequest(BaseModel):
    external_post_id: str = Field(min_length=1)
    external_url: str | None = None


class NextPublishResponse(BaseModel):
    window: str
    now: datetime
    next_publish_time: datetime
    immediate: bool


class PublishJobView(BaseModel):
    """完整 Job（含 attempts）+ 存储侧信息 + 域护栏结论。"""

    job: PublishJob
    row_version: int
    render_manifest_id: str | None = None
    preflight_report: PreflightReport | None = Field(
        default=None,
        description="展示用历史报告（最近一次预检/被拦时落库）；提交判定始终以实时重跑为准",
    )
    issues: list[str] = Field(default_factory=list)


def _view(stored: StoredPublishJob) -> PublishJobView:
    return PublishJobView(
        job=stored.job,
        row_version=stored.row_version,
        render_manifest_id=stored.render_manifest_id,
        preflight_report=(
            None
            if stored.preflight_report is None
            else PreflightReport.model_validate(stored.preflight_report)
        ),
        issues=[f"{i.kind}:{i.ref}:{i.detail}" for i in validate_publish_job(stored.job)],
    )


class CannotPublish(Exception):
    """平台未注册规则集/连接器/执行器 → 409（组合根配置问题，不是用户输入问题）。"""


class PreflightRequired(Exception):
    """未跑过预检就提交 → 409。**fail-closed**：没有媒体探针就无从判断能不能发。"""


class PreflightBlocked(Exception):
    """预检不通过 → 409，且 executor 一次都不会被调用。"""

    def __init__(self, message: str, report: PreflightReport) -> None:
        super().__init__(message)
        self.report = report

    def summary(self) -> list[str]:
        """阻塞项摘要（ERROR/FATAL）——UI 直接看得到该修什么。"""
        return [
            f"{f.check}:{f.severity}:{f.detail}"
            for f in self.report.findings
            if f.severity in (ReviewSeverity.ERROR, ReviewSeverity.FATAL)
        ]


class DbPublishGateway:
    def __init__(
        self,
        engine: Engine,
        *,
        executors: dict[PublishPlatform, PublishExecutor] | None = None,
        connectors: dict[PublishPlatform, PublishConnector] | None = None,
        specs: dict[PublishPlatform, PlatformPublishSpec] | None = None,
    ) -> None:
        self._engine = engine
        self._executors = executors or default_publish_executors()
        self._connectors = connectors or default_publish_connectors()
        self._specs = specs or DEFAULT_PUBLISH_SPECS

    # —— 建任务（幂等）——

    def create(self, request: PublishJobCreate) -> tuple[PublishJob, bool]:
        """返回 (Job, 是否新建)。同幂等键命中即返回既有 Job——同内容绝不建第二个任务。"""
        metadata_digest = metadata_digest_of(request.metadata)
        # copy_index≥1 才把 #copy{n} 折进窗口派生**不同**键（§5：有意的副本才是新 Job）。
        window = (
            request.publishing_window
            if request.copy_index == 0
            else f"{request.publishing_window}#copy{request.copy_index}"
        )
        key = compute_copy_idempotency_key(
            account_id=request.account_id,
            platform=request.platform,
            render_digest=request.media_digest,
            metadata_digest=metadata_digest,
            scheduled_window=request.publishing_window,
            copy_index=request.copy_index,
        )
        try:
            with session_scope(self._engine) as s:
                repo = PublishJobRepository(s)
                existing = repo.find_by_idempotency_key(key)
                if existing is not None:
                    return existing.job, False
                now = _now()
                job = new_publish_job(
                    id=new_id(),
                    account_id=request.account_id,
                    platform=request.platform,
                    method=request.method,
                    render_digest=request.media_digest,
                    metadata_digest=metadata_digest,
                    scheduled_window=window,
                    created_at=now,
                )
                if job.idempotency_key != key:  # 派生窗口与副本键公式必须自洽
                    raise CannotPublish("幂等键推导不一致（窗口派生与副本键公式不匹配）")
                stored = repo.create(
                    job,
                    publish_metadata=request.metadata.model_dump(mode="json"),
                    render_manifest_id=request.render_manifest_id,
                )
                return stored.job, True
        except DuplicateError:
            # 并发窗口：查不到→建时撞唯一键。按幂等语义重读既有 Job 返回，绝不冒 500。
            pass
        with session_scope(self._engine) as s:
            raced = PublishJobRepository(s).find_by_idempotency_key(key)
            if raced is None:  # 唯一键冲突却查不到——不该发生，交由上层 409 而非静默
                raise CannotPublish("幂等键冲突但未找到既有任务（存储不一致）")
            return raced.job, False

    # —— 预检 ——

    def preflight(self, job_id: str, request: PreflightRequest) -> PreflightResponse:
        """跑预检并**持久化探针 + 报告**——submit 放行前会用同一探针重跑，预检不是一次性通行证。

        **元数据取自入库的 `publish_metadata`，不从请求体读**（`PreflightRequest` 已无该字段）：
        这样本端点展示的报告与 submit 的判定输入是**同一份**，不会分叉。元数据参与幂等键、
        建任务后不可变，要改就换新任务。
        """
        with session_scope(self._engine) as s:
            repo = PublishJobRepository(s)
            stored = repo.get_for_update(job_id)
            job = stored.job
            if stored.publish_metadata is None:
                # create() 恒写入元数据 → None 只可能是存储不一致，不静默用空元数据糊过去。
                raise CannotPublish(f"job {job_id!r} 缺少入库元数据（存储不一致）——建任务时必写")
            metadata = PublishMetadata.model_validate(stored.publish_metadata)
            report = self._run_preflight(job.platform, request.probe, metadata)
            target = job
            if not report.publishable and job.state is PublishState.PENDING:
                assert_transition(job.state, PublishState.PREFLIGHT_BLOCKED)
                target = job.model_copy(
                    update={"state": PublishState.PREFLIGHT_BLOCKED, "updated_at": _now()}
                )
            stored = repo.update(
                target,
                expected_row_version=stored.row_version,
                media_probe=request.probe.model_dump(mode="json"),
                preflight_report=report.model_dump(mode="json"),
            )
            return PreflightResponse(report=report, job=stored.job)

    def _run_preflight(
        self, platform: PublishPlatform, probe: PublishMediaProbe, metadata: PublishMetadata
    ) -> PreflightReport:
        spec = self._specs.get(platform)
        connector = self._connectors.get(platform)
        if spec is None or connector is None:
            raise CannotPublish(f"平台 {platform} 未注册规则集/连接器")
        return run_preflight(
            probe, metadata, spec, connector.capabilities(), id=new_id(), created_at=_now()
        )

    def _enforce_preflight(
        self,
        repo: PublishJobRepository,
        stored: StoredPublishJob,
        job: PublishJob,
        *,
        now: datetime,
    ) -> tuple[StoredPublishJob, PublishJob]:
        """发布前置门：用持久化的探针 + **当前**连接器能力重跑预检。

        预检不是一次性通行证——授权可能已过期、账号可能已被封禁，所以每次提交都重算。
        不通过 → Job 置/保持 PREFLIGHT_BLOCKED 并抛 `PreflightBlocked`（executor 不被调用）。

        **调用方契约（务必遵守）**：被拦时本函数已在**当前事务**里 staged 了
        「PREFLIGHT_BLOCKED 状态 + 新的失败报告」，然后才抛 `PreflightBlocked`。调用方必须
        **先吞下这个异常、让事务正常提交，再到 `session_scope` 块外抛出**；若让异常穿透
        `session_scope`，rollback 会把拦截结果一并吞掉——Job 停在 PENDING、`preflight_report`
        列还是上一份 `publishable=true` 的旧报告（这正是本次修复的缺陷成因）。

        遗留（本次不做）：VF-501 的审批门（ALWAYS / NEW_TEMPLATE_ONLY / AUTO 策略 +
        `is_approval_valid`）尚未接进这条路径——发布前"是否已人工批准且审批未失效"目前不校验。
        """
        metadata = stored.publish_metadata
        probe = stored.media_probe
        if probe is None or metadata is None:
            raise PreflightRequired(
                f"job {job.id!r} 尚未通过发布前检查；"
                "请先 POST /v1/publish-jobs/{job_id}/preflight（需提供成片媒体探针）"
            )
        report = self._run_preflight(
            job.platform,
            PublishMediaProbe.model_validate(probe),
            PublishMetadata.model_validate(metadata),
        )
        if report.publishable:
            return stored, job
        target = job
        if job.state is not PublishState.PREFLIGHT_BLOCKED:
            assert_transition(job.state, PublishState.PREFLIGHT_BLOCKED)
            target = job.model_copy(
                update={"state": PublishState.PREFLIGHT_BLOCKED, "updated_at": now}
            )
        repo.update(
            target,
            expected_row_version=stored.row_version,
            preflight_report=report.model_dump(mode="json"),
        )
        raise PreflightBlocked(f"job {job.id!r} 预检未通过，拒绝提交", report)

    # —— 提交（幂等硬拦）——

    def submit(self, job_id: str) -> SubmitResponse:
        """提交发帖。**整段在行锁内**：取锁 → 读最新 → 预检门 → 幂等门 → executor → 写回。

        **被拦时的两段式（同事务提交 + 块外抛错）**：`_enforce_preflight` 不通过时会先在
        当前事务里 staged「PREFLIGHT_BLOCKED + 新失败报告」再抛异常。这里必须把
        `PreflightBlocked` **接住**、让 `with` 正常退出（事务提交，拦截结果真正落库），
        然后到块外重新抛出。否则 `session_scope` 的 rollback 会连拦截写入一起回滚，Job 停在
        PENDING、`preflight_report` 列滞留旧的 `publishable=true`——展示误导 UI。
        判定本身始终 fail-closed，与落不落库无关：每次 submit 都实时重跑预检。

        注意**不要**改成"持锁期间另开一个连接/事务写同一行"：第二个连接的 UPDATE 会阻塞在
        外层的 `FOR UPDATE` 行锁上，自己等死自己。单事务方案没有这个问题，且拦截写入与判定
        在同一把行锁内原子完成。

        取舍（登记为遗留）：行锁横跨 `executor.submit()` 调用。Fake 执行器是瞬时的，没问题；
        接真实执行器（HTTP/浏览器/真机，秒级甚至分钟级）时应改成**「预留-提交」两段式**
        ——先在短事务里把 Job 原子地标成"提交中"并写入预留令牌（参照 VF-006 熔断器的
        single-probe reservation 先例），释放锁后再做外部调用，回来用令牌收尾。本次不实现。
        """
        blocked: PreflightBlocked | None = None
        with session_scope(self._engine) as s:
            repo = PublishJobRepository(s)
            # 行锁：并发的第二方阻塞在这里，拿到锁时已能看到对方提交后的状态
            stored = repo.get_for_update(job_id)
            job = stored.job
            executor = self._executors.get(job.platform)
            if executor is None:
                raise CannotPublish(f"平台 {job.platform} 未注册执行器")

            now = _now()
            if job.state in (PublishState.PENDING, PublishState.PREFLIGHT_BLOCKED):
                # **预检门**：离开 PENDING/PREFLIGHT_BLOCKED 前强制重跑预检（同一能力源）。
                # 不通过 → 置/保持 PREFLIGHT_BLOCKED + 409，executor 一次都不调用。
                try:
                    stored, job = self._enforce_preflight(repo, stored, job, now=now)
                except PreflightBlocked as exc:
                    # 拦截写入已 staged 在本事务；正常退出 with → 先提交，再到块外抛。
                    blocked = exc
            if blocked is None:
                return self._submit_after_gate(repo, stored, job, executor, now=now)
        assert blocked is not None  # 所有未被拦的路径都已在 with 内 return
        raise blocked

    def _submit_after_gate(
        self,
        repo: PublishJobRepository,
        stored: StoredPublishJob,
        job: PublishJob,
        executor: PublishExecutor,
        *,
        now: datetime,
    ) -> SubmitResponse:
        """预检门放行后的提交本体（仍在 `submit` 的行锁事务内）：幂等门 → executor → 写回。"""
        if job.state is not PublishState.UPLOADING:
            # 非法起点（含终态、已提交态）由 domain 迁移表拒 → 409
            assert_transition(job.state, PublishState.UPLOADING)
            job = job.model_copy(update={"state": PublishState.UPLOADING, "updated_at": now})
        if not can_submit(job):
            # durable latch：attempts 里已有 external_post_token → 绝不再发
            raise IllegalPublishTransition(f"job {job.id!r} 已提交过——拒绝重复发布（§5/§13 幂等）")

        result = executor.submit(job)  # 外部副作用：受行锁保护，同一 Job 不会并发进入
        if result.status is PublishExecStatus.OK and result.external_post_token:
            submitted = record_submission(
                job,
                external_post_token=result.external_post_token,
                request_digest=job.idempotency_key,
                now=now,
            )
            stored = repo.update(submitted, expected_row_version=stored.row_version)
            return SubmitResponse(
                job=stored.job,
                executor_status=str(result.status),
                idempotent_replay=result.idempotent_replay,
                detail=result.detail,
            )

        if result.status in (
            PublishExecStatus.CHALLENGE,
            PublishExecStatus.AUTH_REQUIRED,
        ):
            # 挑战/授权失败 → 人工，绝不绕过（§4.5/§13）
            target = PublishState.WAITING_FOR_HUMAN
        else:
            target = PublishState.FAILED
        assert_transition(job.state, target)
        moved = job.model_copy(update={"state": target, "updated_at": now})
        stored = repo.update(moved, expected_row_version=stored.row_version)
        return SubmitResponse(
            job=stored.job,
            executor_status=str(result.status),
            detail=result.detail,
        )

    # —— 对账（绝不重发）——

    def reconcile(self, job_id: str) -> ReconcileResponse:
        with session_scope(self._engine) as s:
            repo = PublishJobRepository(s)
            stored = repo.get_for_update(job_id)
            job = stored.job
            executor = self._executors.get(job.platform)
            if executor is None:
                raise CannotPublish(f"平台 {job.platform} 未注册执行器")
            status = executor.query_status(job)
            reconciled = reconcile_publish(
                job,
                found_external_post=status.found_post,
                now=_now(),
                external_id=status.external_post_id,
                external_url=status.external_url,
            )
            stored = repo.update(reconciled, expected_row_version=stored.row_version)
            return ReconcileResponse(
                job=stored.job,
                found_post=status.found_post,
                attempts_count=len(stored.job.attempts),
            )

    # —— 人工完成 ——

    def manual_complete(self, job_id: str, request: ManualCompleteRequest) -> PublishJob:
        with session_scope(self._engine) as s:
            repo = PublishJobRepository(s)
            stored = repo.get_for_update(job_id)
            done = mark_manually_completed(
                stored.job,
                external_id=request.external_post_id,
                external_url=request.external_url,
                now=_now(),
            )
            return repo.update(done, expected_row_version=stored.row_version).job

    # —— 查询 ——

    def get(self, job_id: str) -> PublishJobView:
        with session_scope(self._engine) as s:
            return _view(PublishJobRepository(s).get(job_id))

    def list(
        self,
        *,
        state: PublishState | None,
        platform: PublishPlatform | None,
        account_id: str | None,
        limit: int,
    ) -> list[PublishJobView]:
        with session_scope(self._engine) as s:
            return [
                _view(x)
                for x in PublishJobRepository(s).list(
                    state=state, platform=platform, account_id=account_id, limit=limit
                )
            ]


router = APIRouter(prefix="/v1", tags=["publish"])


def get_publish_gateway(request: Request) -> DbPublishGateway:
    return request.app.state.publish_gateway


GatewayDep = Annotated[DbPublishGateway, Depends(get_publish_gateway)]


def _raise_http(exc: Exception) -> HTTPException:
    if isinstance(exc, PreflightBlocked):
        return HTTPException(
            status_code=409,
            detail={"message": str(exc), "blocking_findings": exc.summary()},
        )
    if isinstance(exc, PreflightRequired):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, IllegalPublishTransition):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, VersionConflictError):
        return HTTPException(status_code=409, detail=f"并发状态迁移冲突: {exc}")
    if isinstance(exc, CannotPublish):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    raise exc


_HANDLED = (
    PreflightBlocked,
    PreflightRequired,
    IllegalPublishTransition,
    VersionConflictError,
    CannotPublish,
    NotFoundError,
)


@router.post("/publish-jobs")
def create_publish_job(
    body: PublishJobCreate, gateway: GatewayDep, response: Response
) -> PublishJob:
    job, created = gateway.create(body)
    response.status_code = 201 if created else 200
    return job


@router.get("/publish-jobs")
def list_publish_jobs(
    gateway: GatewayDep,
    state: PublishState | None = None,
    platform: PublishPlatform | None = None,
    account_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PublishJobView]:
    return gateway.list(state=state, platform=platform, account_id=account_id, limit=limit)


@router.get("/publish-calendar/next")
def next_publish(
    window: Annotated[str, Query(min_length=1)] = "immediate",
    now: datetime | None = None,
) -> NextPublishResponse:
    """纯 domain 预览：给定发布窗口与当前时刻，下一次可发布的时刻（支持跨零点窗口）。"""
    at = now or _now()
    try:
        target = next_publish_time(window, at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return NextPublishResponse(
        window=window, now=at, next_publish_time=target, immediate=target == at
    )


@router.get("/publish-jobs/{job_id}")
def get_publish_job(job_id: str, gateway: GatewayDep) -> PublishJobView:
    try:
        return gateway.get(job_id)
    except NotFoundError as exc:
        raise _raise_http(exc) from None


@router.post("/publish-jobs/{job_id}/preflight")
def preflight_publish_job(
    job_id: str, body: PreflightRequest, gateway: GatewayDep
) -> PreflightResponse:
    try:
        return gateway.preflight(job_id, body)
    except _HANDLED as exc:
        raise _raise_http(exc) from None


@router.post("/publish-jobs/{job_id}/submit")
def submit_publish_job(job_id: str, gateway: GatewayDep) -> SubmitResponse:
    try:
        return gateway.submit(job_id)
    except _HANDLED as exc:
        raise _raise_http(exc) from None


@router.post("/publish-jobs/{job_id}/reconcile")
def reconcile_publish_job(job_id: str, gateway: GatewayDep) -> ReconcileResponse:
    try:
        return gateway.reconcile(job_id)
    except _HANDLED as exc:
        raise _raise_http(exc) from None


@router.post("/publish-jobs/{job_id}/manual-complete")
def manual_complete_publish_job(
    job_id: str, body: ManualCompleteRequest, gateway: GatewayDep
) -> PublishJob:
    try:
        return gateway.manual_complete(job_id, body)
    except _HANDLED as exc:
        raise _raise_http(exc) from None


__all__ = [
    "DEFAULT_PUBLISH_SPECS",
    "CannotPublish",
    "DbPublishGateway",
    "PreflightBlocked",
    "PreflightRequired",
    "PublishJobCreate",
    "default_publish_connectors",
    "default_publish_executors",
    "metadata_digest_of",
    "router",
]
