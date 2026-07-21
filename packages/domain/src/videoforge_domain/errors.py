class DomainError(Exception):
    """领域逻辑错误基类。"""


class InsufficientSnapshots(DomainError):
    """快照点不足以计算所需的动力学量（velocity 需 ≥2，acceleration 需 ≥3）。"""
