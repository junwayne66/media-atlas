class PersistenceError(Exception):
    """持久化层错误基类。"""


class NotFoundError(PersistenceError):
    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"{kind} not found: {key}")
        self.kind = kind
        self.key = key


class VersionConflictError(PersistenceError):
    """乐观并发冲突：期望版本已被他人更新（51 §1 If-Match 语义）。"""

    def __init__(self, kind: str, key: str, expected_version: int) -> None:
        super().__init__(f"{kind} {key} 版本冲突：expected version {expected_version}")
        self.kind = kind
        self.key = key
        self.expected_version = expected_version


class DuplicateError(PersistenceError):
    """唯一约束冲突（如重复 Artifact id、重复 outbox event id）。"""
