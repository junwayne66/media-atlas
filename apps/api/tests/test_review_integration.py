"""审核决定真库端到端：服务端签名 + 三路"修改即失效" + 篡改可检测。

三路失效（§1.2/§13）：改版本 / 改内容摘要 / 指向别的实体——任一项与审批绑定的不一致即失效。
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from videoforge_api.review import (
    ApprovalValidateRequest,
    DbReviewGateway,
    ReviewDecisionCreate,
)
from videoforge_contracts import ReviewDecisionKind, ReviewScope
from videoforge_contracts.ids import new_id

_NEW_TABLES = ("creative_documents", "review_decisions", "publish_jobs", "performance_snapshots")


@pytest.fixture(autouse=True)
def _clean_new_tables(migrated_engine: Engine) -> Iterator[None]:
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_NEW_TABLES)} CASCADE"))


def _create(entity_id: str) -> ReviewDecisionCreate:
    return ReviewDecisionCreate(
        decision=ReviewDecisionKind.APPROVED,
        scope=ReviewScope.PACKAGE,
        entity_id=entity_id,
        entity_version=2,
        content_digest="a" * 64,
        reviewer_id="reviewer-1",
        policy_snapshot_id="policy-1",
    )


def test_approval_is_valid_only_for_the_exact_reviewed_content(migrated_engine: Engine):
    gw = DbReviewGateway(migrated_engine)
    entity_id = new_id()
    decision = gw.create(_create(entity_id))
    assert decision.signature  # 签名由服务端算，调用方无从伪造绑定

    current = ApprovalValidateRequest(
        current_entity_version=2,
        current_content_digest="a" * 64,
        current_entity_id=entity_id,
    )
    ok = gw.validate(decision.id, current)
    assert ok.valid and ok.issues == []

    # ① 版本改了 → 失效
    bumped = gw.validate(decision.id, current.model_copy(update={"current_entity_version": 3}))
    assert not bumped.valid
    assert any(i.startswith("APPROVAL_STALE") for i in bumped.issues)

    # ② 内容改了 → 失效
    edited = gw.validate(
        decision.id, current.model_copy(update={"current_content_digest": "b" * 64})
    )
    assert not edited.valid
    assert any(i.startswith("APPROVAL_STALE") for i in edited.issues)

    # ③ 指向别的实体 → 失效（门层纵深防御）
    other = gw.validate(decision.id, current.model_copy(update={"current_entity_id": new_id()}))
    assert not other.valid


def test_tampered_record_is_detected(migrated_engine: Engine):
    """直接改库里的 payload（绕过 API）→ 签名重算不一致，护栏报 SIGNATURE_MISMATCH。"""
    gw = DbReviewGateway(migrated_engine)
    entity_id = new_id()
    decision = gw.create(_create(entity_id))

    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE review_decisions "
                "SET payload = jsonb_set(payload, '{entity_version}', '99') "
                "WHERE id = :id"
            ),
            {"id": decision.id},
        )

    result = gw.validate(
        decision.id,
        ApprovalValidateRequest(current_entity_version=99, current_content_digest="a" * 64),
    )
    assert not result.valid
    assert any(i.startswith("SIGNATURE_MISMATCH") for i in result.issues)


def test_list_for_entity_returns_decisions(migrated_engine: Engine):
    gw = DbReviewGateway(migrated_engine)
    entity_id = new_id()
    first = gw.create(_create(entity_id))
    second = gw.create(
        _create(entity_id).model_copy(update={"decision": ReviewDecisionKind.CHANGES_REQUESTED})
    )
    ids = {d.id for d in gw.list_for_entity(entity_id, 50)}
    assert ids == {first.id, second.id}
    assert gw.list_for_entity(new_id(), 50) == []
