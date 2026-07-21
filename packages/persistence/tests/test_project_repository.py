import pytest
from factories import make_project
from sqlalchemy import Engine, select

from videoforge_persistence import (
    DuplicateError,
    NotFoundError,
    ProjectRepository,
    VersionConflictError,
    session_scope,
)
from videoforge_persistence.tables import OutboxEventRow, ProjectRow


def test_create_then_get_roundtrips_contract(session) -> None:
    repo = ProjectRepository(session)
    project = make_project()
    repo.create(project)
    session.flush()
    assert repo.get(project.id) == project


def test_get_missing_raises(session) -> None:
    with pytest.raises(NotFoundError):
        ProjectRepository(session).get("nope")


def test_create_duplicate_id_raises_duplicate(session) -> None:
    repo = ProjectRepository(session)
    project = make_project()
    repo.create(project)
    with pytest.raises(DuplicateError):
        repo.create(make_project(id=project.id))


def test_update_missing_project_raises_not_found(session) -> None:
    """幽灵 id 是 404 语义，不得与版本冲突（409/412）混淆。"""
    with pytest.raises(NotFoundError):
        ProjectRepository(session).update(make_project(), expected_version=1)


def test_concurrent_update_conflicts(migrated_engine: Engine) -> None:
    """DoD：并发版本冲突。两个读者同版本读入，后写者必须失败。"""
    project = make_project()
    with session_scope(migrated_engine) as s:
        ProjectRepository(s).create(project)

    with session_scope(migrated_engine) as s1:
        reader1 = ProjectRepository(s1).get(project.id)
        ProjectRepository(s1).update(
            reader1.model_copy(update={"title": "writer-1"}),
            expected_version=reader1.version,
        )

    with pytest.raises(VersionConflictError):
        with session_scope(migrated_engine) as s2:
            ProjectRepository(s2).update(
                project.model_copy(update={"title": "writer-2"}),
                expected_version=project.version,
            )

    with session_scope(migrated_engine) as s3:
        final = ProjectRepository(s3).get(project.id)
    assert final.title == "writer-1"
    assert final.version == 2


def test_update_writes_outbox_in_same_transaction(migrated_engine: Engine) -> None:
    project = make_project()
    with session_scope(migrated_engine) as s:
        ProjectRepository(s).create(project)
        current = ProjectRepository(s).get(project.id)  # 同事务内可见
        ProjectRepository(s).update(
            current.model_copy(update={"title": "更新后"}), expected_version=current.version
        )

    with session_scope(migrated_engine) as s:
        rows = s.scalars(select(OutboxEventRow).order_by(OutboxEventRow.occurred_at)).all()
        events = [(r.event_type, r.payload) for r in rows]  # commit 会过期实例，作用域内取值
    assert [t for t, _ in events] == ["project.created", "project.updated"]
    assert events[1][1]["title"] == "更新后"
    assert events[1][1]["version"] == 2


def test_rollback_discards_domain_write_and_outbox(migrated_engine: Engine) -> None:
    """DoD：rollback。事务失败时领域写与 outbox 事件都不得残留。"""
    project = make_project()
    with pytest.raises(RuntimeError, match="boom"):
        with session_scope(migrated_engine) as s:
            ProjectRepository(s).create(project)
            s.flush()
            raise RuntimeError("boom")

    with session_scope(migrated_engine) as s:
        assert s.get(ProjectRow, project.id) is None
        assert list(s.scalars(select(OutboxEventRow))) == []
