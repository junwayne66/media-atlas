"""0006 四表仓储：创作产物版本 / 审核决定 / 发布任务 / 表现快照。

**红线专测**：`test_publish_job_roundtrip_keeps_attempts_and_token` ——存→读→再存后
attempts 与 external_post_token 一条不丢。这不是形式：token 是 `domain.has_submitted` 的
durable latch，剥离它就等于允许恢复回路二次发帖（VF-503 verifier 警告）。
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from videoforge_contracts import (
    PerformanceSnapshot,
    PublishMethod,
    PublishPlatform,
    PublishState,
    ReviewDecision,
    ReviewDecisionKind,
    ReviewScope,
)
from videoforge_contracts.ids import new_id
from videoforge_domain.publish_job import (
    has_submitted,
    new_publish_job,
    reconcile_publish,
    record_submission,
)
from videoforge_domain.review_policy import compute_approval_signature
from videoforge_persistence.creation import (
    DOC_BRIEF,
    DOC_SCRIPT_VERSION,
    CreativeDocumentRepository,
)
from videoforge_persistence.errors import VersionConflictError
from videoforge_persistence.performance_store import PerformanceSnapshotRepository
from videoforge_persistence.publish import PublishJobRepository
from videoforge_persistence.review import ReviewDecisionRepository

_NEW_TABLES = (
    "creative_documents",
    "review_decisions",
    "publish_jobs",
    "performance_snapshots",
)
_NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_new_tables(migrated_engine: Engine) -> Iterator[None]:
    """0006 的表不在共享 conftest 的清理清单里——本模块自清，不改既有 conftest。"""
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_NEW_TABLES)} CASCADE"))


def _job(**overrides):
    kwargs = {
        "id": new_id(),
        "account_id": "acct-1",
        "platform": PublishPlatform.TIKTOK,
        "method": PublishMethod.OFFICIAL_API,
        "render_digest": "a" * 64,
        "metadata_digest": "b" * 64,
        "scheduled_window": "immediate",
        "created_at": _NOW,
    }
    kwargs.update(overrides)
    return new_publish_job(**kwargs)


# --- 创作产物 -----------------------------------------------------------------


def test_creative_document_versions_increment_per_kind(session: Session) -> None:
    repo = CreativeDocumentRepository(session)
    project_id = new_id()
    first = repo.add(
        id=new_id(),
        project_id=project_id,
        kind=DOC_BRIEF,
        payload={"objective": "v1"},
        created_at=_NOW,
    )
    second = repo.add(
        id=new_id(),
        project_id=project_id,
        kind=DOC_BRIEF,
        payload={"objective": "v2"},
        created_at=_NOW,
    )
    other_kind = repo.add(
        id=new_id(),
        project_id=project_id,
        kind=DOC_SCRIPT_VERSION,
        payload={"sentences": []},
        created_at=_NOW,
    )
    assert (first.doc_version, second.doc_version) == (1, 2)
    assert other_kind.doc_version == 1  # 版本按 kind 独立自增

    assert repo.latest(project_id, DOC_BRIEF).payload == {"objective": "v2"}
    assert repo.get_version(project_id, DOC_BRIEF, 1).payload == {"objective": "v1"}
    assert len(repo.list(project_id)) == 3
    assert len(repo.list(project_id, DOC_BRIEF)) == 2
    assert repo.find_latest(new_id(), DOC_BRIEF) is None


# --- 审核决定 -----------------------------------------------------------------


def test_review_decision_roundtrip_preserves_signature(session: Session) -> None:
    entity_id = new_id()
    signature = compute_approval_signature(
        entity_id=entity_id,
        entity_version=3,
        content_digest="c" * 64,
        decision=ReviewDecisionKind.APPROVED,
        scope=ReviewScope.PACKAGE.value,
        reviewer_id="reviewer-1",
        policy_snapshot_id="policy-1",
    )
    decision = ReviewDecision(
        id=new_id(),
        decision=ReviewDecisionKind.APPROVED,
        scope=ReviewScope.PACKAGE,
        entity_id=entity_id,
        entity_version=3,
        content_digest="c" * 64,
        reviewer_id="reviewer-1",
        policy_snapshot_id="policy-1",
        signature=signature,
        created_at=_NOW,
    )
    repo = ReviewDecisionRepository(session)
    repo.create(decision)
    session.flush()

    loaded = repo.get(decision.id)
    assert loaded.signature == signature
    assert loaded == decision
    assert [d.id for d in repo.list_for_entity(entity_id)] == [decision.id]


# --- 发布任务（红线）----------------------------------------------------------


def test_publish_job_roundtrip_keeps_attempts_and_token(session: Session) -> None:
    """存→读→再存：attempts 与 external_post_token 一条不丢（幂等 latch 不能被剥离）。"""
    repo = PublishJobRepository(session)
    stored = repo.create(_job())
    job = stored.job

    uploading = job.model_copy(update={"state": PublishState.UPLOADING, "updated_at": _NOW})
    stored = repo.update(uploading, expected_row_version=stored.row_version)

    submitted = record_submission(
        stored.job, external_post_token="tok-abc", request_digest="req-1", now=_NOW
    )
    stored = repo.update(submitted, expected_row_version=stored.row_version)

    # 第一轮往返
    reloaded = repo.get(job.id)
    assert len(reloaded.job.attempts) == 1
    assert reloaded.job.attempts[0].external_post_token == "tok-abc"
    assert has_submitted(reloaded.job)

    # 再存一次（对账 → 成功态），attempts 仍完整
    done = reconcile_publish(reloaded.job, found_external_post=True, now=_NOW, external_id="post-1")
    stored = repo.update(done, expected_row_version=reloaded.row_version)
    final = repo.get(job.id)
    assert final.job.state is PublishState.SUCCEEDED_RECONCILED
    assert [a.external_post_token for a in final.job.attempts] == ["tok-abc"]
    assert has_submitted(final.job)
    assert final.job.external_post_id == "post-1"


def test_publish_job_idempotency_key_lookup_and_optimistic_lock(session: Session) -> None:
    repo = PublishJobRepository(session)
    stored = repo.create(_job(), publish_metadata={"language": "zh-CN"})
    found = repo.find_by_idempotency_key(stored.job.idempotency_key)
    assert found is not None and found.job.id == stored.job.id
    assert found.publish_metadata == {"language": "zh-CN"}
    assert repo.find_by_idempotency_key("nope") is None

    moved = stored.job.model_copy(update={"state": PublishState.UPLOADING, "updated_at": _NOW})
    repo.update(moved, expected_row_version=stored.row_version)
    with pytest.raises(VersionConflictError):  # 陈旧行版本 → 并发迁移冲突
        repo.update(moved, expected_row_version=stored.row_version)


def test_publish_job_find_by_external_post_id(session: Session) -> None:
    repo = PublishJobRepository(session)
    stored = repo.create(_job())
    uploading = stored.job.model_copy(update={"state": PublishState.UPLOADING, "updated_at": _NOW})
    stored = repo.update(uploading, expected_row_version=stored.row_version)
    submitted = record_submission(
        stored.job, external_post_token="tok", request_digest="r", now=_NOW
    )
    stored = repo.update(submitted, expected_row_version=stored.row_version)
    done = reconcile_publish(stored.job, found_external_post=True, now=_NOW, external_id="ext-42")
    repo.update(done, expected_row_version=stored.row_version)

    hit = repo.find_by_external_post_id(
        account_id="acct-1", platform=PublishPlatform.TIKTOK, external_post_id="ext-42"
    )
    assert hit is not None and hit.job.id == stored.job.id
    assert (
        repo.find_by_external_post_id(
            account_id="acct-1", platform=PublishPlatform.TIKTOK, external_post_id="other"
        )
        is None
    )


# --- 表现快照 -----------------------------------------------------------------


def _snapshot(age: float, views: int | None) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        id=new_id(),
        platform=PublishPlatform.TIKTOK,
        platform_post_id="post-x",
        account_id="acct-1",
        observed_at=_NOW,
        age_hours=age,
        views=views,
        source_confidence=1.0,
    )


def test_performance_snapshot_capture_is_idempotent_and_keeps_null(session: Session) -> None:
    repo = PerformanceSnapshotRepository(session)
    first, created = repo.create_if_absent(_snapshot(24.0, 100))
    assert created
    again, created_again = repo.create_if_absent(_snapshot(24.0, 999))
    assert not created_again
    assert again.id == first.id and again.views == 100  # 幂等返回既有，不覆盖观测

    # null 指标往返仍是 None（绝不补 0）
    repo.create_if_absent(_snapshot(1.0, None))
    session.flush()
    ages = {s.age_hours: s.views for s in repo.list_for_post("post-x")}
    assert ages == {1.0: None, 24.0: 100}
    assert len(repo.list_for_account(account_id="acct-1", platform=PublishPlatform.TIKTOK)) == 2
