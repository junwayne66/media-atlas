import pytest
from source_asset_factories import make_file_asset, make_url_asset

from videoforge_contracts import SourceDisposition
from videoforge_persistence import (
    NotFoundError,
    SourceAssetRepository,
    VersionConflictError,
    session_scope,
)


def test_create_get_roundtrip_keeps_full_contract(session) -> None:
    repo = SourceAssetRepository(session)
    asset = make_url_asset()
    repo.create(asset)
    session.flush()
    got = repo.get(asset.id)
    assert got == asset
    # attempts 轨迹（可解释性）不能在往返中丢失
    assert got.acquisition is not None
    assert got.acquisition.attempts[0].connector == "download.f2"


def test_get_missing_raises_not_found(session) -> None:
    with pytest.raises(NotFoundError):
        SourceAssetRepository(session).get("missing")


def test_find_existing_by_platform_and_content_id(session) -> None:
    repo = SourceAssetRepository(session)
    asset = make_url_asset()
    repo.create(asset)
    session.flush()
    assert repo.find_existing(platform="douyin", content_id=asset.content_id) == asset
    assert repo.find_existing(platform="tiktok", content_id=asset.content_id) is None
    assert repo.find_existing(platform="douyin", content_id="other") is None


def test_find_existing_by_file_sha256(session) -> None:
    repo = SourceAssetRepository(session)
    asset = make_file_asset()
    repo.create(asset)
    session.flush()
    assert repo.find_existing(file_sha256=asset.file_sha256) == asset
    assert repo.find_existing(file_sha256="b" * 64) is None


def test_manual_imports_may_share_content_id(session) -> None:
    """手工导入的 content_id 是文件名——同名不同文件必须都能存在（去重靠哈希）。"""
    repo = SourceAssetRepository(session)
    repo.create(make_file_asset(file_sha256="a" * 64))
    repo.create(make_file_asset(file_sha256="b" * 64))
    session.flush()
    assert len(repo.list(platform="manual")) == 2


def test_optimistic_lock_conflict(migrated_engine) -> None:
    with session_scope(migrated_engine) as s:
        repo = SourceAssetRepository(s)
        asset = make_url_asset()
        repo.create(asset)
    with session_scope(migrated_engine) as s:
        repo = SourceAssetRepository(s)
        updated = repo.update(asset.model_copy(update={"project_ids": ["p1"]}), expected_version=1)
        assert updated.version == 2
    with session_scope(migrated_engine) as s:
        with pytest.raises(VersionConflictError):
            SourceAssetRepository(s).update(asset, expected_version=1)


def test_update_missing_raises_not_found(session) -> None:
    with pytest.raises(NotFoundError):
        SourceAssetRepository(session).update(make_url_asset(), expected_version=1)


def test_list_filters_and_orders_by_created_at_desc(migrated_engine) -> None:
    from datetime import UTC, datetime

    with session_scope(migrated_engine) as s:
        repo = SourceAssetRepository(s)
        old = make_url_asset(content_id="1", created_at=datetime(2026, 7, 20, tzinfo=UTC))
        new = make_url_asset(content_id="2", created_at=datetime(2026, 7, 24, tzinfo=UTC))
        tiktok = make_url_asset(platform="tiktok", content_id="3")
        imported = make_file_asset()
        for a in (old, new, tiktok, imported):
            repo.create(a)
    with session_scope(migrated_engine) as s:
        repo = SourceAssetRepository(s)
        douyin = repo.list(platform="douyin")
        assert [a.id for a in douyin] == [new.id, old.id]
        assert len(repo.list(disposition=SourceDisposition.IMPORTED)) == 1
        assert len(repo.list(limit=2)) == 2
        assert [a.id for a in repo.list_with_file_hash()] == [imported.id]
