from datetime import UTC, datetime

from videoforge_contracts import Artifact, CreationMode, Project, StorageRef
from videoforge_persistence import new_id

T0 = datetime(2026, 7, 21, 8, 0, 0, tzinfo=UTC)


def make_project(**overrides) -> Project:
    values = {
        "id": new_id(),
        "title": "AI 芯片新品热点二创",
        "vertical": "ai-tech",
        "source_language": "zh-CN",
        "target_languages": ["en-US"],
        "creation_mode": CreationMode.STRUCTURE_REWRITE,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return Project(**values)


def make_artifact(**overrides) -> Artifact:
    values = {
        "id": new_id(),
        "kind": "source_video",
        "filename": "source.mp4",
        "mime_type": "video/mp4",
        "size_bytes": 1024,
        "sha256": "b" * 64,
        "storage": StorageRef(backend="s3", bucket="videoforge", object_key="k"),
        "created_at": T0,
    }
    values.update(overrides)
    return Artifact(**values)
