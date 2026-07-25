"""DbSourceGateway 真库端到端：解析预览 / 导入幂等 / 手工导入 / 去重分组。

全程零网络：下载连接器默认未配置，路由必然 manual_fallback（诚实处置，非静默失败）。
"""

from datetime import UTC, datetime

from sqlalchemy import Engine, select

from videoforge_api.sources import (
    DbSourceGateway,
    ImportFileRequest,
    ImportUrlRequest,
    ResolveRequest,
)
from videoforge_contracts import (
    CreationMode,
    Project,
    ProjectStatus,
    SourceAssetKind,
    SourceDisposition,
)
from videoforge_contracts.ids import new_id
from videoforge_persistence import ProjectRepository, SourceAssetRepository, session_scope
from videoforge_persistence.tables import OutboxEventRow

_DOUYIN = "https://www.douyin.com/video/7412345678901234567"


def _make_project(engine: Engine) -> Project:
    now = datetime(2026, 7, 25, tzinfo=UTC)
    project = Project(
        id=new_id(),
        title="演示项目",
        vertical="ai-tech",
        source_language="zh-CN",
        target_languages=["en-US"],
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        status=ProjectStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    with session_scope(engine) as s:
        ProjectRepository(s).create(project)
    return project


def test_resolve_preview_three_input_classes(migrated_engine: Engine) -> None:
    gw = DbSourceGateway(migrated_engine)
    ok = gw.resolve(ResolveRequest(input=_DOUYIN))
    assert ok.resolvable and ok.platform == "douyin" and ok.content_id

    short = gw.resolve(ResolveRequest(input="https://v.douyin.com/abc123/"))
    assert short.needs_expansion and short.error_code == "NEEDS_EXPANSION"
    assert not short.resolvable

    bad = gw.resolve(ResolveRequest(input="https://example.com/whatever"))
    assert not bad.resolvable and bad.error_code == "UNRESOLVABLE_INPUT"
    assert bad.reason  # 处置必须可解释


def test_import_url_is_idempotent_and_records_attempts(migrated_engine: Engine) -> None:
    gw = DbSourceGateway(migrated_engine)
    asset, created = gw.import_url(ImportUrlRequest(input=_DOUYIN))
    assert created
    assert asset.disposition is SourceDisposition.MANUAL_FALLBACK
    assert asset.acquisition is not None and asset.acquisition.manual_fallback
    # 可解释轨迹：两个下载器都试过且都是「未配置」，而非静默失败
    assert [a.connector for a in asset.acquisition.attempts] == [
        "download.f2",
        "download.yt_dlp",
    ]
    assert {a.status for a in asset.acquisition.attempts} == {"unconfigured"}

    again, created_again = gw.import_url(ImportUrlRequest(input=_DOUYIN))
    assert not created_again
    assert again.id == asset.id  # 同 URL 两次 → 同一素材

    with session_scope(migrated_engine) as s:
        events = [
            e.event_type
            for e in s.scalars(
                select(OutboxEventRow).where(OutboxEventRow.aggregate_id == asset.id)
            )
        ]
    assert events == ["source.imported"]  # 只在新建时发一次


def test_import_url_short_link_and_unresolvable_are_persisted_with_reason(
    migrated_engine: Engine,
) -> None:
    gw = DbSourceGateway(migrated_engine)
    short, _ = gw.import_url(ImportUrlRequest(input="https://vm.tiktok.com/ZSabc123/"))
    assert short.disposition is SourceDisposition.NEEDS_EXPANSION and short.reason

    bad, _ = gw.import_url(ImportUrlRequest(input="随手写的一句话"))
    assert bad.disposition is SourceDisposition.UNRESOLVABLE
    assert bad.error_code == "UNRESOLVABLE_INPUT" and bad.platform == "unknown"


def test_import_url_attaches_to_project(migrated_engine: Engine) -> None:
    project = _make_project(migrated_engine)
    gw = DbSourceGateway(migrated_engine)
    asset, _ = gw.import_url(ImportUrlRequest(input=_DOUYIN, project_id=project.id))
    assert asset.project_ids == [project.id]
    with session_scope(migrated_engine) as s:
        assert ProjectRepository(s).get(project.id).source_asset_ids == [asset.id]


def test_import_file_hashes_and_dedups(migrated_engine: Engine, tmp_path) -> None:
    gw = DbSourceGateway(migrated_engine)
    media = tmp_path / "demo.mp4"
    media.write_bytes(b"fake-media-bytes")
    asset, created = gw.import_file(ImportFileRequest(path=str(media)))
    assert created
    assert asset.kind is SourceAssetKind.LOCAL_FILE
    assert asset.disposition is SourceDisposition.IMPORTED
    assert asset.platform == "manual" and asset.file_sha256

    again, created_again = gw.import_file(ImportFileRequest(path=str(media)))
    assert not created_again and again.id == asset.id


def test_import_file_missing_path_raises(migrated_engine: Engine, tmp_path) -> None:
    from videoforge_api.sources import LocalFileMissing

    gw = DbSourceGateway(migrated_engine)
    try:
        gw.import_file(ImportFileRequest(path=str(tmp_path / "nope.mp4")))
    except LocalFileMissing as exc:
        assert "不存在" in str(exc)
    else:  # pragma: no cover - 失败路径
        raise AssertionError("缺文件必须报错，不能建一条无文件的 IMPORTED 素材")


def test_import_file_same_content_different_path_is_one_asset(
    migrated_engine: Engine, tmp_path
) -> None:
    """同内容不同路径 → find_existing(file_sha256) 命中，不重复建记录。"""
    gw = DbSourceGateway(migrated_engine)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"identical-bytes")
    b.write_bytes(b"identical-bytes")
    asset_a, _ = gw.import_file(ImportFileRequest(path=str(a)))
    asset_b, created_b = gw.import_file(ImportFileRequest(path=str(b)))
    assert not created_b and asset_b.id == asset_a.id


def test_duplicate_groups_group_same_hash_without_deleting(
    migrated_engine: Engine, tmp_path
) -> None:
    """两条来自不同平台链接的素材，其本地文件哈希相同 → 成一组，且都保留。"""
    gw = DbSourceGateway(migrated_engine)
    asset_a, _ = gw.import_url(ImportUrlRequest(input=_DOUYIN))
    asset_b, _ = gw.import_url(
        ImportUrlRequest(input="https://www.tiktok.com/@u/video/7412345678901234567")
    )
    digest = "c" * 64
    with session_scope(migrated_engine) as s:
        repo = SourceAssetRepository(s)
        for asset in (asset_a, asset_b):
            repo.update(
                asset.model_copy(
                    update={
                        "disposition": SourceDisposition.IMPORTED,
                        "reason": "人工下载后关联本地文件",
                        "local_path": f"/media/{asset.id}.mp4",
                        "file_sha256": digest,
                    }
                ),
                expected_version=asset.version,
            )

    groups = gw.duplicate_groups()
    assert len(groups) == 1
    assert set(groups[0].member_asset_ids) == {asset_a.id, asset_b.id}
    assert groups[0].layers == ["FILE"]
    # 绝不删除来源记录
    assert len(gw.list_assets(None, None, 50)) == 2
