import pytest
from factories import make_artifact

from videoforge_persistence import ArtifactRepository, DuplicateError, NotFoundError


def test_add_then_get_roundtrips_contract(session) -> None:
    repo = ArtifactRepository(session)
    artifact = make_artifact()
    repo.add(artifact)
    assert repo.get(artifact.id) == artifact


def test_duplicate_id_rejected(session) -> None:
    repo = ArtifactRepository(session)
    artifact = make_artifact()
    repo.add(artifact)
    with pytest.raises(DuplicateError):
        repo.add(make_artifact(id=artifact.id))


def test_unknown_project_fk_raises_not_found(session) -> None:
    """外键无效 = 引用的 project 不存在（404 语义），与主键重复分开报。"""
    with pytest.raises(NotFoundError):
        ArtifactRepository(session).add(make_artifact(project_id="ghost"))


def test_size_bytes_supports_large_media(session) -> None:
    """源视频/成片超 2GiB 是常态，列必须是 BigInteger。"""
    repo = ArtifactRepository(session)
    artifact = make_artifact(size_bytes=3 * 1024**3)
    repo.add(artifact)
    assert repo.get(artifact.id).size_bytes == 3 * 1024**3


def test_same_hash_different_sources_both_kept(session) -> None:
    """30 §7：同哈希可去重分组，但不同来源记录不得合并丢失。"""
    repo = ArtifactRepository(session)
    a1 = make_artifact(sha256="c" * 64, filename="from_douyin.mp4")
    a2 = make_artifact(sha256="c" * 64, filename="from_tiktok.mp4")
    repo.add(a1)
    repo.add(a2)
    found = repo.find_by_sha256("c" * 64)
    assert {a.id for a in found} == {a1.id, a2.id}
    assert {a.filename for a in found} == {"from_douyin.mp4", "from_tiktok.mp4"}


def test_repository_exposes_no_mutation_api() -> None:
    """不可变对象仓储只增不改不删。"""
    public = {m for m in dir(ArtifactRepository) if not m.startswith("_")}
    assert public == {"add", "get", "find_by_sha256"}
