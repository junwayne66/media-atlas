"""画面文字本地化合同（docs/modules/43 §6）。

VF-403 目标：**决策 + 计划**层——把 VF-203 已聚合的 `TextTrack`（含 CAPTION/TITLE/
LOWER_THIRD/UI/SCENE_TEXT/BRAND_MARK 六类）按语言/授权/置信度/运动映射到具体策略：
REDRAW / REPLACE_OVERLAY / INFO_CARD_FALLBACK / KEEP_AS_IS / SKIP / LOCALIZE_ANNOTATION。

**红线**（§6.1）：BRAND_MARK 绝不作为普通翻译文字（品牌/授权风险）；UI 避免伪造产品界面；
SCENE_TEXT 不重要可保留。**图像重绘**（真 Clean Plate / inpainting）不在此层——那是渲染
层，通过 provider-sdk 的 TextRedraw/CleanPlate 端口分派；本层输出**计划**（Provider 领任务）。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import TextTrackKind


class TextLocalizationStrategy(StrEnum):
    """一条 TextTrack 的本地化策略。"""

    REDRAW = "REDRAW"  # 清除原文字 + 重绘目标语言（Clean Plate + 排字）
    REPLACE_OVERLAY = "REPLACE_OVERLAY"  # 半透明底 + 目标语言覆盖（不重绘背景）
    INFO_CARD_FALLBACK = "INFO_CARD_FALLBACK"  # 品牌化信息卡覆盖（低质量回退）
    KEEP_AS_IS = "KEEP_AS_IS"  # 保留原文字，不译（默认 SCENE_TEXT 不重要时）
    SKIP = "SKIP"  # 不处理（如 BRAND_MARK 未授权 → 交人工）
    LOCALIZE_ANNOTATION = "LOCALIZE_ANNOTATION"  # 侧边旁注/贴片翻译，不覆盖原文字


class CleanPlateMethod(StrEnum):
    """Clean Plate 生成方法（§6.2）。"""

    BACKGROUND_ESTIMATE = "BACKGROUND_ESTIMATE"  # 多帧估计背景（无遮挡场景）
    AUTHORIZED_INPAINT = "AUTHORIZED_INPAINT"  # 授权的 inpainting pipeline
    SKIP = "SKIP"  # 无需 Clean Plate（REPLACE_OVERLAY / INFO_CARD_FALLBACK / KEEP_AS_IS）


class TextLocalizationReviewReason(StrEnum):
    """需人工审核的原因（provider 与 domain 都可能置）。"""

    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    OCCLUSION_HIGH = "OCCLUSION_HIGH"
    MOTION_UNSUPPORTED = "MOTION_UNSUPPORTED"
    LICENSE_UNCONFIRMED = "LICENSE_UNCONFIRMED"  # BRAND_MARK / UI 授权未确认
    LAYOUT_OVERFLOW = "LAYOUT_OVERFLOW"  # 目标语言更长且不能缩短
    CLEAN_PLATE_FAILED = "CLEAN_PLATE_FAILED"
    GLOSSARY_MISS = "GLOSSARY_MISS"  # 术语表未命中但源含疑似专名
    UNKNOWN_KIND = "UNKNOWN_KIND"  # TextTrackKind.UNKNOWN 需人工分类


class TextLocalizationKindPolicy(ContractModel):
    """单个 TextTrackKind 的策略配置——把 §6.1 的表格数据化，可按模板/账号覆盖。

    - default_strategy：kind 的默认策略。
    - min_confidence_for_auto：低于此 OCR 置信度就走回退（INFO_CARD_FALLBACK 或人工）。
    - allow_redraw：True 才允许自动重绘；False 会退到 REPLACE_OVERLAY / INFO_CARD。
    - fallback_strategy：低质量/回退时用的策略。
    - requires_license_check：BRAND_MARK / UI 常需授权确认。
    """

    kind: TextTrackKind
    default_strategy: TextLocalizationStrategy
    min_confidence_for_auto: float = Field(default=0.7, ge=0.0, le=1.0)
    allow_redraw: bool = True
    fallback_strategy: TextLocalizationStrategy = TextLocalizationStrategy.INFO_CARD_FALLBACK
    requires_license_check: bool = False


class TextLocalizationPolicy(ContractModel):
    """跨 kind 的完整策略集（每种 kind 一条 KindPolicy）+ 全局阈值 + 默认信息卡。"""

    id: str = Field(min_length=1)
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    per_kind: list[TextLocalizationKindPolicy] = Field(default_factory=list)
    max_occlusion_for_redraw: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="遮挡比 > 此值即禁用重绘，回退",
    )
    max_layout_expansion_ratio: float = Field(
        default=1.3,
        gt=1.0,
        le=3.0,
        description="目标语言长度相对源的最大扩张倍数（超即回退，§6.2 缩短而非无限缩小字号）",
    )
    info_card_style_ref: str | None = Field(
        default=None,
        description="回退信息卡的样式引用（如 template 或 asset id）",
    )
    version: int = Field(default=1, ge=1)
    created_at: datetime

    @model_validator(mode="after")
    def _check_per_kind_unique(self) -> "TextLocalizationPolicy":
        seen: set[str] = set()
        for p in self.per_kind:
            key = p.kind.value
            if key in seen:
                raise ValueError(f"per_kind 中 TextTrackKind 重复：{key}")
            seen.add(key)
        return self


class CleanPlateRequest(ContractModel):
    """一次 Clean Plate 请求（供 provider-sdk CleanPlateProvider 消费）。"""

    id: str = Field(min_length=1)
    source_track_id: str = Field(min_length=1)
    source_artifact_id: str = Field(min_length=1)
    frame_start_ms: int = Field(ge=0)
    frame_end_ms: int = Field(ge=0)
    method: CleanPlateMethod
    license_ref: str | None = Field(
        default=None,
        description="AUTHORIZED_INPAINT 的授权凭证引用",
    )

    @model_validator(mode="after")
    def _check_span_and_license(self) -> "CleanPlateRequest":
        if self.frame_end_ms < self.frame_start_ms:
            raise ValueError("frame_end_ms 必须 ≥ frame_start_ms")
        if self.method is CleanPlateMethod.AUTHORIZED_INPAINT and not self.license_ref:
            raise ValueError(
                "AUTHORIZED_INPAINT 必须携带 license_ref（否则违反 docs/README §4 授权/清理红线）"
            )
        return self


class TextTrackLocalizationDecision(ContractModel):
    """对一条 TextTrack 的本地化决策。"""

    source_track_id: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    source_kind: TextTrackKind
    target_language: str = Field(min_length=1)
    strategy: TextLocalizationStrategy
    translated_text: str | None = Field(
        default=None,
        description="KEEP_AS_IS / SKIP / BRAND_MARK 未授权时可为 None",
    )
    clean_plate_request_id: str | None = Field(
        default=None,
        description="策略需要 Clean Plate 时引用其 id",
    )
    layout_expansion_ratio: float | None = Field(
        default=None,
        ge=0.0,
        description="翻译后文本长度 / 源长度；> policy.max 走回退",
    )
    needs_review: bool = False
    review_reasons: list[TextLocalizationReviewReason] = Field(default_factory=list)
    rationale: str = Field(min_length=1, description="选择该策略的原因（人可读）")


class TextLocalizationPlan(ContractModel):
    """一次画面文字本地化计划（多轨决策 + Clean Plate 请求集合）。"""

    id: str = Field(min_length=1)
    source_text_track_set_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    decisions: list[TextTrackLocalizationDecision] = Field(default_factory=list)
    clean_plate_requests: list[CleanPlateRequest] = Field(default_factory=list)
    created_at: datetime
    provider: str | None = None

    @model_validator(mode="after")
    def _check_refs(self) -> "TextLocalizationPlan":
        # decision.clean_plate_request_id 若非空必须能解析到本 plan 的 requests
        req_ids = {r.id for r in self.clean_plate_requests}
        for d in self.decisions:
            if d.clean_plate_request_id and d.clean_plate_request_id not in req_ids:
                raise ValueError(
                    f"decision {d.source_track_id!r} 引用未知 clean_plate_request "
                    f"{d.clean_plate_request_id!r}"
                )
        # source_track_id 在 decisions 里唯一
        seen: set[str] = set()
        for d in self.decisions:
            if d.source_track_id in seen:
                raise ValueError(f"同一 source_track_id 出现两次：{d.source_track_id!r}")
            seen.add(d.source_track_id)
        return self
