"""合同对象 <-> 行对象的转换。仓储只对外暴露合同类型，不泄露 ORM 实体。

dump 用 python 模式：DateTime 列要原生 datetime；StrEnum 是 str 子类可直接入
String 列；嵌套模型变 dict 后进 JSONB。
"""

from videoforge_contracts import Artifact, Project
from videoforge_persistence.tables import ArtifactRow, ProjectRow


def project_to_row(project: Project) -> ProjectRow:
    return ProjectRow(**project.model_dump())


def row_to_project(row: ProjectRow) -> Project:
    return Project.model_validate(
        {c.name: getattr(row, c.name) for c in ProjectRow.__table__.columns}
    )


def artifact_to_row(artifact: Artifact) -> ArtifactRow:
    return ArtifactRow(**artifact.model_dump())


def row_to_artifact(row: ArtifactRow) -> Artifact:
    return Artifact.model_validate(
        {c.name: getattr(row, c.name) for c in ArtifactRow.__table__.columns}
    )
