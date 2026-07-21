import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

DEFAULT_DATABASE_URL = "postgresql+psycopg://videoforge:videoforge@localhost:5432/videoforge"


def create_engine_from_env(url: str | None = None) -> Engine:
    return create_engine(url or os.environ.get("VIDEOFORGE_DATABASE_URL", DEFAULT_DATABASE_URL))


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """一个事务边界：正常退出提交，异常回滚后重抛。

    领域写与 outbox 事件必须在同一个 scope 内完成（docs/implementation/50 §11）。
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
