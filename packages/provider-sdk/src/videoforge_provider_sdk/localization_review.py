"""语言一致性检查端口 + Fake（docs/modules/43 §12：源/目标 Claim/专名/语义一致）。

纯规则能查的（数字、否定标记数）在 domain；**语义级**一致（Claim 意义、专名是否被保留/
误译、指代）需 LLM → 本端口分派，真实实现属 stop-condition 延后。

`FakeLocalizationConsistencyProvider` 做**浅层确定性**专名保留检查（源专名是否出现在译文），
诚实标注不做深层语义；产出 `LocalizationQAFinding`（contracts-only，不 import domain）。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    LocalizationQACheck,
    LocalizationQAFinding,
    QASeverity,
)


class ConsistencyStatus(StrEnum):
    OK = "OK"
    UNCONFIGURED = "UNCONFIGURED"
    FAILED = "FAILED"


class ConsistencyErrorCode(StrEnum):
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConsistencyCheckRequest:
    """一句的语义一致性检查请求。"""

    sentence_id: str
    source: str
    target: str
    source_lang: str
    target_lang: str
    source_entities: tuple[str, ...] = ()  # 需在译文中保留的专名/产品名


@dataclass(frozen=True)
class ConsistencyCheckResult:
    status: ConsistencyStatus
    findings: list[LocalizationQAFinding] = field(default_factory=list)
    error_code: ConsistencyErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class LocalizationConsistencyProvider(Protocol):
    """§12 语义一致性端口。"""

    name: str

    def check(self, request: ConsistencyCheckRequest) -> ConsistencyCheckResult: ...

    def health_check(self) -> ConsistencyCheckResult: ...


class UnconfiguredLocalizationConsistencyProvider:
    """诚实占位：无真实语义一致性 LLM，返回 UNCONFIGURED（不产 findings）。"""

    def __init__(self, *, name: str = "consistency.unconfigured") -> None:
        self.name = name

    def check(self, request: ConsistencyCheckRequest) -> ConsistencyCheckResult:
        return ConsistencyCheckResult(
            status=ConsistencyStatus.UNCONFIGURED,
            error_code=ConsistencyErrorCode.ENGINE_UNAVAILABLE,
            error_detail=f"provider {self.name!r} 未配置真实语义一致性 LLM",
        )

    def health_check(self) -> ConsistencyCheckResult:
        return ConsistencyCheckResult(
            status=ConsistencyStatus.UNCONFIGURED,
            error_code=ConsistencyErrorCode.ENGINE_UNAVAILABLE,
        )


class FakeLocalizationConsistencyProvider:
    """确定性 Fake：浅层专名保留检查（大小写不敏感包含）。

    - 源专名未出现在译文 → `PROPER_NOUN_CONSISTENCY` finding（MAJOR：可能是合法转写/翻译，
      交人工核，不自动 BLOCK）。
    - **不做深层语义**（Claim 意义/指代需真 LLM）——warnings 明示；不伪造深层结论。
    - deep-copy 输入；无内部状态。
    """

    def __init__(self, *, name: str = "consistency.fake") -> None:
        self.name = name

    def check(self, request: ConsistencyCheckRequest) -> ConsistencyCheckResult:
        req = deepcopy(request)
        target_lower = req.target.lower()
        findings: list[LocalizationQAFinding] = []
        for entity in req.source_entities:
            if entity and entity.lower() not in target_lower:
                findings.append(
                    LocalizationQAFinding(
                        sentence_id=req.sentence_id,
                        check=LocalizationQACheck.PROPER_NOUN_CONSISTENCY,
                        severity=QASeverity.MAJOR,
                        detail=f"专名 {entity!r} 未在译文中出现（可能漏译/误译，须人工核）",
                        evidence={"entity": entity},
                    )
                )
        return ConsistencyCheckResult(
            status=ConsistencyStatus.OK,
            findings=findings,
            warnings=["Fake 一致性：仅浅层专名包含检查，未做深层语义/Claim 核对"],
        )

    def health_check(self) -> ConsistencyCheckResult:
        return ConsistencyCheckResult(status=ConsistencyStatus.OK)


__all__ = [
    "ConsistencyCheckRequest",
    "ConsistencyCheckResult",
    "ConsistencyErrorCode",
    "ConsistencyStatus",
    "FakeLocalizationConsistencyProvider",
    "LocalizationConsistencyProvider",
    "UnconfiguredLocalizationConsistencyProvider",
]
