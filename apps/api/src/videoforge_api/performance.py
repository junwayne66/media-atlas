"""效果反馈 API（docs/modules/44 §10/§11；VF-601..603 的 REST 面，**零网络 Fake 回采**）。

三条立场：

1. **null≠0 全程保真**：连接器不上报的指标进库是 JSON null、出 API 还是 null；基线/分组/相关
   都由 domain 排除空值。端点不做任何"补 0""兜底"加工。
2. **非 OK 不落库不编造**：限流/未授权/未找到/未配置一律结构化错误响应，绝不写一条半真快照。
3. **归因只做读模型**：`build_account_baseline` / `build_dashboard` / `build_learning_report`
   全在 domain——样本不足不排序、账号内相对、关联非因果这些红线由 domain 保证，端点原样透传。

`features` 的组装语义（诚实登记）：能从对应 `publish_job` 取到的（语言 / 发布小时 / 星期）就取，
成片时长从 job 关联的 RenderManifest 取；**取不到的一律留 None**——domain 会把该维度跳过，
而不是把未知当成某个默认分组。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from videoforge_api.demo_metrics import default_metrics_connectors
from videoforge_contracts import (
    AccountBaseline,
    LearningReport,
    MetricField,
    PerformanceDashboard,
    PerformanceFeatures,
    PerformanceGroupStat,
    PerformanceSnapshot,
    PublishPlatform,
    PublishState,
    RenderManifest,
    VideoPerformanceRecord,
)
from videoforge_domain.learning_signals import build_learning_report, validate_learning_report
from videoforge_domain.performance import (
    DEFAULT_SNAPSHOT_AGES_HOURS,
    validate_performance_snapshot,
)
from videoforge_domain.performance_dashboard import (
    build_account_baseline,
    build_dashboard,
    insufficient_sample_groups,
    rank_groups,
    validate_dashboard,
)
from videoforge_persistence import NotFoundError, session_scope
from videoforge_persistence.creation import DOC_RENDER_MANIFEST, CreativeDocumentRepository
from videoforge_persistence.performance_store import PerformanceSnapshotRepository
from videoforge_persistence.publish import PublishJobRepository
from videoforge_provider_sdk.metrics_connector import MetricsConnector, MetricsFetchStatus

# 非 OK 抓取 → HTTP 状态（结构化拒绝，不落库不编造）
_FETCH_STATUS_HTTP: dict[MetricsFetchStatus, int] = {
    MetricsFetchStatus.RATE_LIMITED: 429,
    MetricsFetchStatus.AUTH_REQUIRED: 409,
    MetricsFetchStatus.UNCONFIGURED: 409,
    MetricsFetchStatus.NOT_FOUND: 404,
    MetricsFetchStatus.FAILED: 502,
}


class CaptureRequest(BaseModel):
    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    post_id: str = Field(min_length=1)
    age_hours: float = Field(ge=0)


class CaptureResponse(BaseModel):
    snapshot: PerformanceSnapshot
    created: bool = Field(description="False = 同 (post, age) 已抓过，幂等返回既有快照")
    issues: list[str] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    dashboard: PerformanceDashboard
    baseline: AccountBaseline
    ranked_groups: list[PerformanceGroupStat] = Field(
        description="只含样本足够的分组（样本不足绝不排序）"
    )
    insufficient_groups: list[PerformanceGroupStat] = Field(description="样本不足：只报不排")
    record_count: int
    issues: list[str] = Field(default_factory=list)


class LearningResponse(BaseModel):
    report: LearningReport
    record_count: int
    issues: list[str] = Field(default_factory=list)


class DbPerformanceGateway:
    def __init__(
        self,
        engine: Engine,
        *,
        connectors: dict[PublishPlatform, MetricsConnector] | None = None,
    ) -> None:
        self._engine = engine
        self._connectors: dict[PublishPlatform, MetricsConnector] = dict(
            connectors or default_metrics_connectors()
        )

    # —— 采集 ——

    def capture(self, request: CaptureRequest) -> CaptureResponse:
        connector = self._connectors.get(request.platform)
        if connector is None:
            raise MetricsFetchRejected(
                MetricsFetchStatus.UNCONFIGURED, f"平台 {request.platform} 未注册指标连接器"
            )
        result = connector.fetch(
            platform_post_id=request.post_id,
            account_id=request.account_id,
            observed_at=datetime.now(UTC),
            age_hours=request.age_hours,
        )
        if result.status is not MetricsFetchStatus.OK or result.snapshot is None:
            raise MetricsFetchRejected(
                result.status,
                f"抓取未成功（{result.status}）：不落库、不编造指标",
                retry_after_seconds=result.retry_after_seconds,
                error_code=result.error_code,
            )
        snapshot = result.snapshot
        with session_scope(self._engine) as s:
            stored, created = PerformanceSnapshotRepository(s).create_if_absent(snapshot)
        issues = validate_performance_snapshot(stored)
        return CaptureResponse(
            snapshot=stored,
            created=created,
            issues=[f"{i.kind}:{i.ref}:{i.detail}" for i in issues],
        )

    def list_for_post(self, post_id: str) -> list[PerformanceSnapshot]:
        with session_scope(self._engine) as s:
            return PerformanceSnapshotRepository(s).list_for_post(post_id)

    # —— 归因读模型 ——

    def dashboard(
        self,
        *,
        account_id: str,
        platform: PublishPlatform,
        age_hours: float,
        metric: MetricField,
        min_samples: int,
    ) -> DashboardResponse:
        records = self._records(account_id, platform)
        now = datetime.now(UTC)
        dashboard = build_dashboard(
            records,
            account_id=account_id,
            platform=platform,
            age_hours=age_hours,
            metric=metric,
            generated_at=now,
            min_samples=min_samples,
        )
        baseline = build_account_baseline(
            records,
            account_id=account_id,
            platform=platform,
            generated_at=now,
            ages_hours=list(DEFAULT_SNAPSHOT_AGES_HOURS),
            metrics=[metric],
        )
        issues = validate_dashboard(dashboard)
        return DashboardResponse(
            dashboard=dashboard,
            baseline=baseline,
            ranked_groups=rank_groups(dashboard),
            insufficient_groups=insufficient_sample_groups(dashboard),
            record_count=len(records),
            issues=[f"{i.kind}:{i.ref}:{i.detail}" for i in issues],
        )

    def learning_report(
        self,
        *,
        account_id: str,
        platform: PublishPlatform,
        age_hours: float,
        metric: MetricField,
        min_samples: int,
    ) -> LearningResponse:
        records = self._records(account_id, platform)
        report = build_learning_report(
            records,
            account_id=account_id,
            platform=platform,
            age_hours=age_hours,
            metric=metric,
            generated_at=datetime.now(UTC),
            min_samples=min_samples,
        )
        issues = validate_learning_report(report)
        return LearningResponse(
            report=report,
            record_count=len(records),
            issues=[f"{i.kind}:{i.ref}:{i.detail}" for i in issues],
        )

    # —— 内部：库里的快照 + 发布任务 → VideoPerformanceRecord ——

    def _records(self, account_id: str, platform: PublishPlatform) -> list[VideoPerformanceRecord]:
        with session_scope(self._engine) as s:
            snapshots = PerformanceSnapshotRepository(s).list_for_account(
                account_id=account_id, platform=platform
            )
            grouped: dict[str, list[PerformanceSnapshot]] = defaultdict(list)
            for snap in snapshots:
                grouped[snap.platform_post_id].append(snap)
            return [
                self._record_for_post(s, account_id, platform, post_id, snaps)
                for post_id, snaps in sorted(grouped.items())
            ]

    def _record_for_post(
        self,
        session: Session,
        account_id: str,
        platform: PublishPlatform,
        post_id: str,
        snapshots: list[PerformanceSnapshot],
    ) -> VideoPerformanceRecord:
        stored = PublishJobRepository(session).find_by_external_post_id(
            account_id=account_id, platform=platform, external_post_id=post_id
        )
        published_at = self._published_at(snapshots, stored)
        features = self._features(session, stored, published_at)
        return VideoPerformanceRecord(
            id=post_id,
            account_id=account_id,
            platform=platform,
            published_at=published_at,
            features=features,
            snapshots=sorted(snapshots, key=lambda s: s.age_hours),
        )

    @staticmethod
    def _published_at(snapshots: list[PerformanceSnapshot], stored) -> datetime:  # noqa: ANN001
        if stored is not None and stored.job.state in (
            PublishState.SUCCEEDED,
            PublishState.SUCCEEDED_RECONCILED,
        ):
            return stored.job.updated_at
        # 无对应 Job：由最早一张快照倒推（观测时刻 - 年龄）——不猜、不用当前时钟。
        earliest = min(snapshots, key=lambda s: s.age_hours)
        return earliest.observed_at - timedelta(hours=earliest.age_hours)

    @staticmethod
    def _features(
        session: Session,
        stored,  # noqa: ANN001 - StoredPublishJob | None
        published_at: datetime,
    ) -> PerformanceFeatures:
        """能取到的才填，取不到留 None——domain 会跳过该维度（绝不把未知当默认分组）。"""
        if stored is None:
            return PerformanceFeatures()
        metadata = stored.publish_metadata or {}
        duration_ms: int | None = None
        if stored.render_manifest_id:
            try:
                doc = CreativeDocumentRepository(session).get(stored.render_manifest_id)
            except NotFoundError:
                doc = None
            if doc is not None and doc.kind == DOC_RENDER_MANIFEST:
                duration_ms = RenderManifest.model_validate(doc.payload).duration_ms
        return PerformanceFeatures(
            language=metadata.get("language"),
            publish_hour=published_at.hour,
            publish_weekday=published_at.weekday(),
            duration_ms=duration_ms,
        )


class MetricsFetchRejected(Exception):
    """抓取非 OK：结构化拒绝（不落库、不编造指标）。"""

    def __init__(
        self,
        status: MetricsFetchStatus,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        self.error_code = error_code


router = APIRouter(prefix="/v1/performance", tags=["performance"])


def get_performance_gateway(request: Request) -> DbPerformanceGateway:
    return request.app.state.performance_gateway


GatewayDep = Annotated[DbPerformanceGateway, Depends(get_performance_gateway)]


@router.post("/snapshots:capture")
def capture_snapshot(
    body: CaptureRequest, gateway: GatewayDep, response: Response
) -> CaptureResponse:
    try:
        result = gateway.capture(body)
    except MetricsFetchRejected as exc:
        raise HTTPException(
            status_code=_FETCH_STATUS_HTTP.get(exc.status, 502),
            detail={
                "message": str(exc),
                "status": str(exc.status),
                "error_code": exc.error_code,
                "retry_after_seconds": exc.retry_after_seconds,
            },
        ) from None
    response.status_code = 201 if result.created else 200
    return result


@router.get("/snapshots")
def list_snapshots(
    gateway: GatewayDep, post_id: Annotated[str, Query(min_length=1)]
) -> list[PerformanceSnapshot]:
    return gateway.list_for_post(post_id)


@router.get("/dashboard")
def get_dashboard(
    gateway: GatewayDep,
    account_id: Annotated[str, Query(min_length=1)],
    platform: PublishPlatform,
    age_hours: Annotated[float, Query(ge=0)] = 24.0,
    metric: MetricField = MetricField.VIEWS,
    min_samples: Annotated[int, Query(ge=1)] = 5,
) -> DashboardResponse:
    return gateway.dashboard(
        account_id=account_id,
        platform=platform,
        age_hours=age_hours,
        metric=metric,
        min_samples=min_samples,
    )


@router.get("/learning-report")
def get_learning_report(
    gateway: GatewayDep,
    account_id: Annotated[str, Query(min_length=1)],
    platform: PublishPlatform,
    age_hours: Annotated[float, Query(ge=0)] = 24.0,
    metric: MetricField = MetricField.VIEWS,
    min_samples: Annotated[int, Query(ge=1)] = 8,
) -> LearningResponse:
    return gateway.learning_report(
        account_id=account_id,
        platform=platform,
        age_hours=age_hours,
        metric=metric,
        min_samples=min_samples,
    )


__all__ = [
    "DbPerformanceGateway",
    "MetricsFetchRejected",
    "router",
]
