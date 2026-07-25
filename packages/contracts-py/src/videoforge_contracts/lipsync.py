"""口型同步合同（docs/modules/43 §10）。

VF-406 目标：**资格判断 + 计划 + 回退**层——把每个配音片段按 §10.1 资格（单主脸、面部
尺寸、遮挡、speaker 概率、时长、转头幅度、配音已对齐）判定能否跑 GPU 局部口型合成
（MuseTalk 类），并为不合格/合成失败的片段按 §10.2 顺序选回退：
原口型相近 Take → 插 B-roll/屏录 → 加快切镜 → 保留非口型配音。

**红线（§10.2 + §13 验收）**：口型**不是阻塞性能力**。任何片段最终都必须落到一个具体、
非阻塞的 `LipSyncMethod`——`KEEP_UNSYNCED`（保留非口型配音）是永远可用的终局回退。合成
失败/QA 不过必须**自动降级**并产生警告，绝不让 Workflow 永久卡住。`lip_sync_mode`：
`OFF`（全部 KEEP_UNSYNCED）/ `AUTO_ELIGIBLE`（合格即自动合成）/ `FORCE_REVIEW`（合格但
强制人工复核）。真实 GPU 合成 + QA 在 provider-sdk 端口分派；本层输出**计划**。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class LipSyncMode(StrEnum):
    """§10.2 口型模式。"""

    OFF = "OFF"  # 不做口型，全部保留非口型配音
    AUTO_ELIGIBLE = "AUTO_ELIGIBLE"  # 合格片段自动合成
    FORCE_REVIEW = "FORCE_REVIEW"  # 合格片段仍强制人工复核后才用


class LipSyncMethod(StrEnum):
    """一个片段最终的口型处理方式（GPU 合成 + §10.2 回退阶梯）。"""

    GPU_SYNTHESIS = "GPU_SYNTHESIS"  # MuseTalk 类局部脸区合成（首选）
    ORIGINAL_TAKE = "ORIGINAL_TAKE"  # 选用原口型相近 Take（回退 1）
    BROLL_COVER = "BROLL_COVER"  # 插 B-roll/屏录覆盖（回退 2）
    FASTER_CUT = "FASTER_CUT"  # 加快切镜避开口型（回退 3）
    KEEP_UNSYNCED = "KEEP_UNSYNCED"  # 保留非口型配音（终局回退，永远可用）


class LipSyncIneligibleReason(StrEnum):
    """§10.1 资格不符原因。"""

    MODE_OFF = "MODE_OFF"  # lip_sync_mode=OFF，不评估
    NO_PRIMARY_FACE = "NO_PRIMARY_FACE"  # 无可用主脸
    MULTIPLE_FACES = "MULTIPLE_FACES"  # 多脸（非单一主脸）
    FACE_TOO_SMALL = "FACE_TOO_SMALL"  # 面部尺寸不足
    OCCLUSION_HIGH = "OCCLUSION_HIGH"  # 遮挡过大
    LOW_SPEAKER_PROBABILITY = "LOW_SPEAKER_PROBABILITY"  # face↔speaker 概率低
    DURATION_OUT_OF_RANGE = "DURATION_OUT_OF_RANGE"  # 片段时长超模型支持范围
    HEAD_TURN_TOO_LARGE = "HEAD_TURN_TOO_LARGE"  # 转头幅度超范围
    DUB_NOT_ALIGNED = "DUB_NOT_ALIGNED"  # 目标配音尚未最终对齐


class LipSyncReviewReason(StrEnum):
    """需人工复核的原因（provider 与 domain 都可能置）。"""

    FORCE_REVIEW = "FORCE_REVIEW"  # mode=FORCE_REVIEW 的强制复核
    QA_FAILED = "QA_FAILED"  # 合成后 QA 未过 → 已降级
    SYNTHESIS_FAILED = "SYNTHESIS_FAILED"  # 合成本身失败 → 已降级
    FALLBACK_USED = "FALLBACK_USED"  # 用了非首选方式，提示复核
    KEPT_UNSYNCED = "KEPT_UNSYNCED"  # 终局保留非口型配音，提示复核


class LipSyncEligibilityCriteria(ContractModel):
    """§10.1 资格阈值（可按模板/模型能力覆盖）。"""

    max_faces: int = Field(default=1, ge=1, description="允许的最大脸数（单主脸=1）")
    min_face_height_ratio: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="面部高度 / 画面高度的最小比（太小 → FACE_TOO_SMALL）",
    )
    max_occlusion_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    min_speaker_probability: float = Field(default=0.6, ge=0.0, le=1.0)
    min_duration_ms: int = Field(default=400, ge=0)
    max_duration_ms: int = Field(default=30000, gt=0)
    max_head_turn_deg: float = Field(default=35.0, ge=0.0, le=180.0)
    require_dub_aligned: bool = True

    @model_validator(mode="after")
    def _check_duration_bounds(self) -> "LipSyncEligibilityCriteria":
        if self.min_duration_ms > self.max_duration_ms:
            raise ValueError(
                f"min_duration_ms({self.min_duration_ms}) 必须 ≤ "
                f"max_duration_ms({self.max_duration_ms})"
            )
        return self


class LipSyncQAReport(ContractModel):
    """§10.2 合成后一致性 QA（边界、肤色、运动、身份）。分数 ∈ [0,1]，越高越好。"""

    boundary_score: float = Field(ge=0.0, le=1.0, description="脸区边界融合")
    skin_tone_score: float = Field(ge=0.0, le=1.0, description="肤色一致")
    motion_score: float = Field(ge=0.0, le=1.0, description="运动/口型自然")
    identity_score: float = Field(ge=0.0, le=1.0, description="身份一致（不换脸）")
    passed: bool = Field(description="是否通过 QA（不过则须降级）")


class LipSyncSegmentDecision(ContractModel):
    """对一个配音片段的口型决策。

    不变量（合同层硬拦）：`GPU_SYNTHESIS` 只能用于合格片段；不合格必须记录原因。
    """

    segment_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    eligible: bool
    ineligible_reasons: list[LipSyncIneligibleReason] = Field(default_factory=list)
    method: LipSyncMethod
    synthesized_artifact_id: str | None = Field(
        default=None,
        description="GPU_SYNTHESIS 成功时的局部脸区产物",
    )
    qa: LipSyncQAReport | None = Field(
        default=None,
        description="GPU_SYNTHESIS 已执行时的 QA 报告",
    )
    fallback_from: LipSyncMethod | None = Field(
        default=None,
        description="从哪个方式降级来的（自动降级记录）",
    )
    needs_review: bool = False
    review_reasons: list[LipSyncReviewReason] = Field(default_factory=list)
    rationale: str = Field(min_length=1, description="该决策的原因（人可读）")

    @model_validator(mode="after")
    def _check_consistency(self) -> "LipSyncSegmentDecision":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        # GPU 合成只能用于合格片段
        if self.method is LipSyncMethod.GPU_SYNTHESIS and not self.eligible:
            raise ValueError("GPU_SYNTHESIS 只能用于 eligible 片段")
        # 不合格必须有原因
        if not self.eligible and not self.ineligible_reasons:
            raise ValueError("eligible=False 必须记录 ineligible_reasons")
        return self


class LipSyncPlan(ContractModel):
    """一次口型同步计划（模式 + 资格阈值 + 逐片段决策）。"""

    id: str = Field(min_length=1)
    localization_variant_id: str = Field(min_length=1)
    mode: LipSyncMode
    criteria: LipSyncEligibilityCriteria = Field(
        default_factory=LipSyncEligibilityCriteria,
    )
    decisions: list[LipSyncSegmentDecision] = Field(default_factory=list)
    created_at: datetime
    provider: str | None = None

    @model_validator(mode="after")
    def _check_unique_segments(self) -> "LipSyncPlan":
        seen: set[str] = set()
        for d in self.decisions:
            if d.segment_id in seen:
                raise ValueError(f"同一 segment_id 出现两次：{d.segment_id!r}")
            seen.add(d.segment_id)
        return self
