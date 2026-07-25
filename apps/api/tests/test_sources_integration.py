"""DbSourceGateway 真库端到端：解析预览 / 导入幂等 / 手工导入 / 去重分组。

全程零网络：下载连接器默认未配置，路由必然 manual_fallback（诚实处置，非静默失败）。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

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
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
)
from videoforge_contracts.ids import new_id
from videoforge_persistence import ProjectRepository, SourceAssetRepository, session_scope
from videoforge_persistence.tables import OutboxEventRow, SourceAssetRow

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


# —— 并发 / 幂等回归（复现 verifier 反例）——


def _count_assets(engine: Engine) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(SourceAssetRow)) or 0


def _imported_events(engine: Engine) -> list[str]:
    with Session(engine) as s:
        return [
            e.aggregate_id
            for e in s.scalars(
                select(OutboxEventRow).where(OutboxEventRow.event_type == "source.imported")
            )
        ]


class _BarrierOnPersistGateway(DbSourceGateway):
    """把「查未命中」与「插入」之间的并发窗口拉到最大：双方都 miss 后才同时插。"""

    def __init__(self, engine: Engine, barrier: threading.Barrier) -> None:
        super().__init__(engine)
        self._barrier = barrier

    def _persist_new(self, asset: SourceAsset, project_id: str | None) -> SourceAsset:
        self._barrier.wait(timeout=30)
        return super()._persist_new(asset, project_id)


class _BarrierOnAttachGateway(DbSourceGateway):
    """双方都读到同一版本后才各自乐观锁更新 —— 必然一方冲突。"""

    def __init__(self, engine: Engine, barrier: threading.Barrier) -> None:
        super().__init__(engine)
        self._barrier = barrier

    def _attach_project(
        self, session: Session, asset: SourceAsset, project_id: str | None
    ) -> SourceAsset:
        self._barrier.wait(timeout=30)
        return super()._attach_project(session, asset, project_id)


def test_concurrent_same_url_import_is_idempotent_not_500(migrated_engine: Engine) -> None:
    """并发同 URL 导入：输家撞唯一索引后重查复用，两边都成功且只有一条素材/一个事件。"""
    barrier = threading.Barrier(2)
    gw = _BarrierOnPersistGateway(migrated_engine, barrier)

    def run() -> tuple[str, bool]:
        asset, created = gw.import_url(ImportUrlRequest(input=_DOUYIN))
        return asset.id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result(timeout=60) for f in [pool.submit(run), pool.submit(run)]]

    ids = {r[0] for r in results}
    assert len(ids) == 1  # 两个响应指向同一素材
    assert {r[1] for r in results} == {True, False}  # 201 + 200 语义
    assert _count_assets(migrated_engine) == 1
    assert _imported_events(migrated_engine) == [next(iter(ids))]


def test_concurrent_attach_different_projects_keeps_both(migrated_engine: Engine) -> None:
    """并发把同一素材挂到不同 Project：乐观锁输家重试，两个 project 都在 project_ids 里。"""
    p1 = _make_project(migrated_engine)
    p2 = _make_project(migrated_engine)
    seed = DbSourceGateway(migrated_engine)
    asset, created = seed.import_url(ImportUrlRequest(input=_DOUYIN))
    assert created

    barrier = threading.Barrier(2)
    gw = _BarrierOnAttachGateway(migrated_engine, barrier)

    def run(project_id: str) -> bool:
        _, created_again = gw.import_url(ImportUrlRequest(input=_DOUYIN, project_id=project_id))
        return created_again

    with ThreadPoolExecutor(max_workers=2) as pool:
        created_flags = [
            f.result(timeout=60) for f in [pool.submit(run, p1.id), pool.submit(run, p2.id)]
        ]

    assert created_flags == [False, False]  # 两边都是命中复用（200），无人 500
    with session_scope(migrated_engine) as s:
        stored = SourceAssetRepository(s).get(asset.id)
        assert set(stored.project_ids) == {p1.id, p2.id}  # 关联不丢
        for project_id in (p1.id, p2.id):
            assert ProjectRepository(s).get(project_id).source_asset_ids == [asset.id]
    assert _count_assets(migrated_engine) == 1


def test_short_link_and_unresolvable_input_are_idempotent(migrated_engine: Engine) -> None:
    """短链 / 垃圾输入没有 content_id，按 sha256(原始输入) 去重：导入三次仍是一条素材。"""
    gw = DbSourceGateway(migrated_engine)
    short_url = "https://v.douyin.com/abc123/"
    junk = "随手写的一句话"

    short_results = [gw.import_url(ImportUrlRequest(input=short_url)) for _ in range(3)]
    assert [c for _, c in short_results] == [True, False, False]
    assert len({a.id for a, _ in short_results}) == 1

    junk_results = [gw.import_url(ImportUrlRequest(input=junk)) for _ in range(3)]
    assert [c for _, c in junk_results] == [True, False, False]
    assert len({a.id for a, _ in junk_results}) == 1

    # 两类互不干扰，各自一条素材、一个事件
    assert short_results[0][0].id != junk_results[0][0].id
    assert _count_assets(migrated_engine) == 2
    assert sorted(_imported_events(migrated_engine)) == sorted(
        [short_results[0][0].id, junk_results[0][0].id]
    )


def test_concurrent_same_short_link_import_is_idempotent(migrated_engine: Engine) -> None:
    """并发同短链：input_digest 部分唯一索引兜底，输家重查复用而非 500。"""
    barrier = threading.Barrier(2)
    gw = _BarrierOnPersistGateway(migrated_engine, barrier)

    def run() -> tuple[str, bool]:
        asset, created = gw.import_url(ImportUrlRequest(input="https://vm.tiktok.com/ZSabc123/"))
        return asset.id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result(timeout=60) for f in [pool.submit(run), pool.submit(run)]]

    assert len({r[0] for r in results}) == 1
    assert {r[1] for r in results} == {True, False}
    assert _count_assets(migrated_engine) == 1
