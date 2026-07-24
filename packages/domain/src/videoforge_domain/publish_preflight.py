"""发布前检查（docs/modules/44 §3 连接器能力 + 预检；§9 元数据规则）。纯函数、可复现。

- `run_preflight(probe, metadata, spec, capability)` → `PreflightReport`：媒体（分辨率/宽高比/
  编码/容器/文件/时长）+ 元数据（标题/描述/标签长度、禁用字符）+ 连接器能力/授权/审核/账号
  逐项检查，算 `publishable`。
- `select_publish_method(capabilities)` → §3 优先级阶梯选可用连接器（MANUAL_EXPORT 终局）。
- `publish_preflight_gate` / `validate_preflight_report`：发布前门 + 一致性护栏。

**红线**：授权未过 / 账号异常 / 方法不可用是 ERROR/FATAL（不静默放行）；未审核客户端只
WARNING（可见性受限，§3.1，仍可发但明示）。本层**只读预检**，不触真实平台（VF-503 起）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    AccountStatus,
    AuthStatus,
    ClientReviewStatus,
    PlatformPublishSpec,
    PreflightCheck,
    PreflightFinding,
    PreflightReport,
    PublishConnectorCapability,
    PublishMediaProbe,
    PublishMetadata,
    PublishMethod,
    ReviewSeverity,
)

# §3 发布连接器优先级阶梯（官方优先，人工导出终局）
DEFAULT_METHOD_PRIORITY: tuple[PublishMethod, ...] = (
    PublishMethod.OFFICIAL_API,
    PublishMethod.OFFICIAL_SHARE_SDK,
    PublishMethod.BROWSER_AUTOMATION,
    PublishMethod.ANDROID_DEVICE,
    PublishMethod.MANUAL_EXPORT,
)

_BLOCKING = (ReviewSeverity.ERROR, ReviewSeverity.FATAL)


class PreflightIssueKind(StrEnum):
    PUBLISHABLE_WITH_BLOCKER = "PUBLISHABLE_WITH_BLOCKER"
    PUBLISHABLE_MISMATCH = "PUBLISHABLE_MISMATCH"  # publishable 与重算门不一致
    PLATFORM_MISMATCH = "PLATFORM_MISMATCH"  # report/spec/capability 平台不一


@dataclass(frozen=True)
class PreflightIssue:
    kind: PreflightIssueKind
    ref: str
    detail: str


def _f(check: PreflightCheck, sev: ReviewSeverity, detail: str,
       **evidence: object) -> PreflightFinding:
    return PreflightFinding(check=check, severity=sev, detail=detail,
                             evidence=dict(evidence))


def run_preflight(
    probe: PublishMediaProbe,
    metadata: PublishMetadata,
    spec: PlatformPublishSpec,
    capability: PublishConnectorCapability,
    *,
    id: str,
    created_at: datetime,
) -> PreflightReport:
    """对成片 + 元数据 + 连接器能力做发布前检查，产出报告（publishable 由门算）。"""
    findings: list[PreflightFinding] = []

    # 平台一致
    if spec.platform is not capability.platform:
        findings.append(_f(
            PreflightCheck.METHOD_UNAVAILABLE, ReviewSeverity.FATAL,
            f"规则集平台 {spec.platform.value} 与连接器 {capability.platform.value} 不一致",
        ))

    # --- 媒体 ---
    if not (spec.min_width <= probe.width <= spec.max_width
            and spec.min_height <= probe.height <= spec.max_height):
        findings.append(_f(
            PreflightCheck.RESOLUTION, ReviewSeverity.ERROR,
            f"分辨率 {probe.width}x{probe.height} 超出 "
            f"[{spec.min_width}x{spec.min_height}, {spec.max_width}x{spec.max_height}]",
        ))
    if probe.aspect_ratio not in spec.allowed_aspect_ratios:
        findings.append(_f(
            PreflightCheck.ASPECT_RATIO, ReviewSeverity.ERROR,
            f"宽高比 {probe.aspect_ratio} 不在允许集 {spec.allowed_aspect_ratios}",
        ))
    if probe.video_codec not in spec.allowed_video_codecs:
        findings.append(_f(
            PreflightCheck.VIDEO_CODEC, ReviewSeverity.ERROR,
            f"视频编码 {probe.video_codec} 不被允许",
        ))
    if probe.audio_codec not in spec.allowed_audio_codecs:
        findings.append(_f(
            PreflightCheck.AUDIO_CODEC, ReviewSeverity.ERROR,
            f"音频编码 {probe.audio_codec} 不被允许",
        ))
    if probe.container not in spec.allowed_containers:
        findings.append(_f(
            PreflightCheck.CONTAINER, ReviewSeverity.ERROR,
            f"容器 {probe.container} 不被允许",
        ))
    size_cap = spec.max_file_size_bytes
    if capability.max_file_size_bytes is not None:
        size_cap = min(size_cap, capability.max_file_size_bytes)
    if probe.file_size_bytes > size_cap:
        findings.append(_f(
            PreflightCheck.FILE_SIZE, ReviewSeverity.ERROR,
            f"文件 {probe.file_size_bytes}B 超上限 {size_cap}B",
        ))
    if not (spec.min_duration_ms <= probe.duration_ms <= spec.max_duration_ms):
        findings.append(_f(
            PreflightCheck.DURATION, ReviewSeverity.ERROR,
            f"时长 {probe.duration_ms}ms 超出 "
            f"[{spec.min_duration_ms}, {spec.max_duration_ms}]",
        ))

    # --- 元数据（§9）---
    if len(metadata.title) > spec.title_max_len:
        findings.append(_f(
            PreflightCheck.TITLE_LENGTH, ReviewSeverity.ERROR,
            f"标题 {len(metadata.title)} 字符超上限 {spec.title_max_len}",
        ))
    hit = [c for c in spec.banned_title_chars if c in metadata.title]
    if hit:
        findings.append(_f(
            PreflightCheck.TITLE_BANNED_CHARS, ReviewSeverity.ERROR,
            f"标题含禁用字符 {hit}",
        ))
    if len(metadata.description) > spec.description_max_len:
        findings.append(_f(
            PreflightCheck.DESCRIPTION_LENGTH, ReviewSeverity.ERROR,
            f"描述 {len(metadata.description)} 字符超上限 {spec.description_max_len}",
        ))
    if len(metadata.tags) > spec.max_tags:
        findings.append(_f(
            PreflightCheck.TAG_COUNT, ReviewSeverity.ERROR,
            f"标签 {len(metadata.tags)} 个超上限 {spec.max_tags}",
        ))
    long_tags = [t for t in metadata.tags if len(t) > spec.tag_max_len]
    if long_tags:
        findings.append(_f(
            PreflightCheck.TAG_LENGTH, ReviewSeverity.ERROR,
            f"标签超长（>{spec.tag_max_len}）：{long_tags}",
        ))

    # --- 连接器能力 / 授权 / 审核 / 账号 ---
    if not capability.available:
        findings.append(_f(
            PreflightCheck.METHOD_UNAVAILABLE, ReviewSeverity.ERROR,
            f"发布方法 {capability.method.value} 当前不可用",
        ))
    if capability.auth_status is not AuthStatus.AUTHORIZED:
        findings.append(_f(
            PreflightCheck.AUTH_STATUS, ReviewSeverity.ERROR,
            f"授权状态 {capability.auth_status.value}（需 AUTHORIZED 才能发布）",
        ))
    if capability.client_review_status is not ClientReviewStatus.APPROVED:
        findings.append(_f(
            PreflightCheck.REVIEW_STATUS, ReviewSeverity.WARNING,
            f"客户端审核 {capability.client_review_status.value}"
            "：发布可受可见性限制（§3.1），须知情",
        ))
    if capability.account_status is AccountStatus.SUSPENDED:
        findings.append(_f(
            PreflightCheck.ACCOUNT_STATUS, ReviewSeverity.FATAL,
            "账号已封禁，不可发布",
        ))
    elif capability.account_status is not AccountStatus.ACTIVE:
        findings.append(_f(
            PreflightCheck.ACCOUNT_STATUS, ReviewSeverity.WARNING,
            f"账号状态 {capability.account_status.value}（非 ACTIVE），须确认",
        ))

    publishable = publish_preflight_gate(findings)
    return PreflightReport(
        id=id, platform=spec.platform, method=capability.method,
        findings=findings, publishable=publishable, created_at=created_at,
    )


def publish_preflight_gate(findings: list[PreflightFinding]) -> bool:
    """发布前门：无 ERROR/FATAL 即可发布（WARNING/INFO 仅告知）。"""
    return not any(f.severity in _BLOCKING for f in findings)


def select_publish_method(
    capabilities: list[PublishConnectorCapability],
    *,
    order: tuple[PublishMethod, ...] = DEFAULT_METHOD_PRIORITY,
) -> PublishConnectorCapability | None:
    """§3 按优先级阶梯选可用连接器。

    可用 = `available` 且（MANUAL_EXPORT 无需授权 / 其它需 AUTHORIZED 且账号未封禁）。
    按 `order` 优先级返回第一个可用的；都不行 → None（调用方走人工导出/暂停）。

    同一方法出现多条能力时取**第一条可用的**（不让前面的不可用条目遮蔽后面可用的）。
    """
    for method in order:
        for cap in capabilities:
            if cap.method is not method or not cap.available:
                continue
            if method is PublishMethod.MANUAL_EXPORT:
                return cap  # 终局回退，无需授权
            if (
                cap.auth_status is AuthStatus.AUTHORIZED
                and cap.account_status is not AccountStatus.SUSPENDED
            ):
                return cap
    return None


def validate_preflight_report(report: PreflightReport) -> list[PreflightIssue]:
    """一致性护栏：publishable 必须与重算门一致，且不与 ERROR/FATAL 并存。"""
    issues: list[PreflightIssue] = []
    has_blocker = any(f.severity in _BLOCKING for f in report.findings)
    if report.publishable and has_blocker:
        issues.append(PreflightIssue(
            PreflightIssueKind.PUBLISHABLE_WITH_BLOCKER, report.id,
            "publishable=True 却含 ERROR/FATAL 发现",
        ))
    if report.publishable != (not has_blocker):
        issues.append(PreflightIssue(
            PreflightIssueKind.PUBLISHABLE_MISMATCH, report.id,
            "publishable 与按 findings 重算的门不一致",
        ))
    return issues


def is_publishable(report: PreflightReport) -> bool:
    return report.publishable and not validate_preflight_report(report)
