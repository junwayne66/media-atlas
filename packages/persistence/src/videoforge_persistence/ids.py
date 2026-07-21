import uuid6


def new_id() -> str:
    """UUIDv7 字符串主键：时间有序、外部不可枚举（docs/implementation/50 §11）。"""
    return str(uuid6.uuid7())
