from datetime import UTC, datetime

import pytest

from videoforge_persistence import (
    AnalysisArtifactRecord,
    AnalysisArtifactRepository,
    AnalysisRunRecord,
    AnalysisRunRepository,
    DuplicateError,
    NotFoundError,
    new_id,
    session_scope,
)

T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _run(project_id: str, **over) -> AnalysisRunRecord:
    values = {
        "id": new_id(),
        "project_id": project_id,
        "source_asset_id": "asset-1",
        "language": "zh-CN",
        "status": "COMPLETED",
        "stages": [{"stage": "transcript", "status": "COMPLETED", "cache_hit": False}],
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(over)
    return AnalysisRunRecord(**values)


def _artifact(**over) -> AnalysisArtifactRecord:
    values = {
        "id": new_id(),
        "project_id": "p1",
        "kind": "transcript",
        "cache_key": "c" * 64,
        "payload": {"id": "t1"},
        "provider": "fake-asr",
        "tool_version": "1",
        "created_at": T0,
    }
    values.update(over)
    return AnalysisArtifactRecord(**values)


def test_run_roundtrip_and_latest(migrated_engine) -> None:
    with session_scope(migrated_engine) as s:
        repo = AnalysisRunRepository(s)
        first = _run("p1", created_at=datetime(2026, 7, 24, tzinfo=UTC))
        second = _run("p1")
        repo.create(first)
        repo.create(second)
        repo.create(_run("p2"))
    with session_scope(migrated_engine) as s:
        repo = AnalysisRunRepository(s)
        assert repo.latest_for_project("p1").id == second.id
        assert repo.get(first.id).stages[0]["stage"] == "transcript"
        with pytest.raises(NotFoundError):
            repo.latest_for_project("p3")


def test_artifact_cache_lookup_by_kind_and_key(session) -> None:
    repo = AnalysisArtifactRepository(session)
    art = _artifact()
    repo.add(art)
    session.flush()
    assert repo.find_cached("transcript", art.cache_key).id == art.id
    # 同 cache_key 不同 kind 不串味
    assert repo.find_cached("video_blueprint", art.cache_key) is None
    assert repo.find_cached("transcript", "d" * 64) is None


def test_artifact_kind_cache_key_is_unique(session) -> None:
    repo = AnalysisArtifactRepository(session)
    repo.add(_artifact())
    session.flush()
    with pytest.raises(DuplicateError):
        repo.add(_artifact())
        session.flush()
