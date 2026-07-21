"""趋势阶段状态机（docs/modules/40 §6）。

EMERGING → RISING → PEAK → SATURATED → DECAYING → ARCHIVED
分类是从子分数与样本量的启发式；合法迁移用于校验状态更新（人工/自动都走它）。
"""

from videoforge_contracts import TrendStage, TrendSubScores

# 少于此样本量时高加速度判为 EMERGING（样本少但起飞快）
_EMERGING_SAMPLE_CEILING = 5

# 阶段线性顺序（40 §6）
_ORDER: tuple[TrendStage, ...] = (
    TrendStage.EMERGING,
    TrendStage.RISING,
    TrendStage.PEAK,
    TrendStage.SATURATED,
    TrendStage.DECAYING,
    TrendStage.ARCHIVED,
)


def _forward_targets(stage: TrendStage) -> frozenset[TrendStage]:
    # 允许前进到任意更晚阶段：观测间隔大时趋势可跨级（如上次 EMERGING、
    # 本次已 SATURATED），故 classify_stage 的输出永远是合法迁移；
    # 不允许倒退，但 DECAYING 可二次起飞回 RISING。
    idx = _ORDER.index(stage)
    targets = set(_ORDER[idx + 1 :])
    if stage == TrendStage.DECAYING:
        targets.add(TrendStage.RISING)
    return frozenset(targets)


# 合法迁移表：前进/跳级 + 归档终态 + DECAYING→RISING 二次起飞
STAGE_TRANSITIONS: dict[TrendStage, frozenset[TrendStage]] = {
    stage: _forward_targets(stage) for stage in _ORDER
}


def can_transition(current: TrendStage, target: TrendStage) -> bool:
    return target in STAGE_TRANSITIONS[current]


class IllegalStageTransition(Exception):
    def __init__(self, current: TrendStage, target: TrendStage) -> None:
        super().__init__(f"非法阶段迁移: {current} -> {target}")
        self.current = current
        self.target = target


def assert_transition(current: TrendStage, target: TrendStage) -> None:
    if current != target and not can_transition(current, target):
        raise IllegalStageTransition(current, target)


def classify_stage(sub_scores: TrendSubScores, *, sample_count: int) -> TrendStage:
    """从子分数与样本量判定阶段（40 §6）。判定顺序即优先级。"""
    s = sub_scores
    if s.decay >= 0.5 or (s.velocity < 0.1 and s.decay >= 0.2):
        return TrendStage.DECAYING
    if s.saturation >= 0.6:
        return TrendStage.SATURATED
    if s.velocity >= 0.6 and s.acceleration < 0.2:
        return TrendStage.PEAK  # 绝对热度高、加速趋零
    if s.acceleration >= 0.5 and sample_count < _EMERGING_SAMPLE_CEILING:
        return TrendStage.EMERGING  # 样本少但加速高
    if s.velocity >= 0.3:
        return TrendStage.RISING
    return TrendStage.EMERGING
