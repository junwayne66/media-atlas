"""审核 API（docs/modules/44 §1.2；VF-501 审核决定 + 版本签名的 REST 面）。

两条立场：

1. **签名由服务端算**，不接受客户端传入 `signature`——签名是"审批绑定到被审内容"的完整性凭据
   （`domain.compute_approval_signature`），让调用方自带签名等于允许伪造绑定。
2. **修改失效语义全在 domain**：`/validate` 只把当前 version + content_digest（+ 可选 entity_id）
   透传给 `is_approval_valid` / `validate_review_decision`，端点不自作聪明加判断，也不缓存结论。

安全边界（承接 VF-501 docstring）：签名是**无密钥**的内容绑定摘要，提供完整性与"改即失效"，
**不提供密码学不可否认性**（HMAC/非对称 + 密钥管理属安全硬化项，接入时走 security 评审）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from videoforge_contracts import ReviewDecision, ReviewDecisionKind, ReviewScope
from videoforge_contracts.ids import new_id
from videoforge_domain.review_policy import (
    compute_approval_signature,
    is_approval_valid,
    validate_review_decision,
)
from videoforge_persistence import NotFoundError, session_scope
from videoforge_persistence.review import ReviewDecisionRepository


class ReviewDecisionCreate(BaseModel):
    decision: ReviewDecisionKind
    scope: ReviewScope
    entity_id: str = Field(min_length=1)
    entity_version: int = Field(ge=1)
    content_digest: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    policy_snapshot_id: str = Field(default="policy-default", min_length=1)
    qc_report_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class ApprovalValidateRequest(BaseModel):
    current_entity_version: int = Field(ge=1)
    current_content_digest: str = Field(min_length=1)
    current_entity_id: str | None = None


class ApprovalValidateResponse(BaseModel):
    valid: bool = Field(description="APPROVED 且签名完整且版本/内容/实体都匹配当前")
    issues: list[str] = Field(default_factory=list)


class DbReviewGateway:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, request: ReviewDecisionCreate) -> ReviewDecision:
        signature = compute_approval_signature(
            entity_id=request.entity_id,
            entity_version=request.entity_version,
            content_digest=request.content_digest,
            decision=request.decision,
            scope=request.scope.value,
            reviewer_id=request.reviewer_id,
            policy_snapshot_id=request.policy_snapshot_id,
        )
        decision = ReviewDecision(
            id=new_id(),
            decision=request.decision,
            scope=request.scope,
            entity_id=request.entity_id,
            entity_version=request.entity_version,
            content_digest=request.content_digest,
            reviewer_id=request.reviewer_id,
            policy_snapshot_id=request.policy_snapshot_id,
            qc_report_ids=list(request.qc_report_ids),
            signature=signature,
            note=request.note,
            created_at=datetime.now(UTC),
        )
        with session_scope(self._engine) as s:
            return ReviewDecisionRepository(s).create(decision)

    def get(self, decision_id: str) -> ReviewDecision:
        with session_scope(self._engine) as s:
            return ReviewDecisionRepository(s).get(decision_id)

    def list_for_entity(self, entity_id: str, limit: int) -> list[ReviewDecision]:
        with session_scope(self._engine) as s:
            return ReviewDecisionRepository(s).list_for_entity(entity_id, limit=limit)

    def validate(
        self, decision_id: str, request: ApprovalValidateRequest
    ) -> ApprovalValidateResponse:
        decision = self.get(decision_id)
        valid = is_approval_valid(
            decision,
            current_version=request.current_entity_version,
            current_content_digest=request.current_content_digest,
            current_entity_id=request.current_entity_id,
        )
        issues = validate_review_decision(
            decision,
            current_version=request.current_entity_version,
            current_content_digest=request.current_content_digest,
        )
        return ApprovalValidateResponse(
            valid=valid,
            issues=[f"{i.kind}:{i.ref}:{i.detail}" for i in issues],
        )


router = APIRouter(prefix="/v1/review-decisions", tags=["review"])


def get_review_gateway(request: Request) -> DbReviewGateway:
    return request.app.state.review_gateway


GatewayDep = Annotated[DbReviewGateway, Depends(get_review_gateway)]


@router.post("")
def create_decision(
    body: ReviewDecisionCreate, gateway: GatewayDep, response: Response
) -> ReviewDecision:
    response.status_code = 201
    return gateway.create(body)


@router.get("")
def list_decisions(
    gateway: GatewayDep,
    entity_id: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReviewDecision]:
    return gateway.list_for_entity(entity_id, limit)


@router.get("/{decision_id}")
def get_decision(decision_id: str, gateway: GatewayDep) -> ReviewDecision:
    try:
        return gateway.get(decision_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"审核决定不存在: {decision_id}") from None


@router.post("/{decision_id}/validate")
def validate_decision(
    decision_id: str, body: ApprovalValidateRequest, gateway: GatewayDep
) -> ApprovalValidateResponse:
    try:
        return gateway.validate(decision_id, body)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"审核决定不存在: {decision_id}") from None


__all__ = ["DbReviewGateway", "ReviewDecisionCreate", "router"]
