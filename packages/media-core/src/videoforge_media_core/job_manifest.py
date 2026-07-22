"""媒体操作的可重放 Job Manifest 与 Activity Cache Key（README §4、docs/modules/41 §11）。

每个媒体操作（探测/转码/抽音/场景检测）产出一份 JobManifest：输入哈希、工具与版本、
规范化配置、输出哈希、schema 版本——据此可逐位重放，也可据 activity_cache_key 命中缓存
避免重复计算。纯数据 + 纯函数，无 I/O。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MANIFEST_SCHEMA_VERSION = "1.0"


def normalize_config(config: dict[str, Any]) -> str:
    """配置 → 规范 JSON（键排序、无多余空白），供哈希/缓存键使用，确保可重放。"""
    return json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def activity_cache_key(
    *,
    input_digest: str,
    provider: str,
    tool_version: str,
    config: dict[str, Any],
    schema_version: str = MANIFEST_SCHEMA_VERSION,
) -> str:
    """Activity Cache Key（41 §11）：
    sha256(input_artifact_digest + provider + model_version + normalized_config + schema_version)。

    换字幕不重跑下载/镜头、换 OCR 模型只重跑 OCR——由本键区分。用 \\x00 分隔避免歧义。
    """
    material = "\x00".join(
        [input_digest, provider, tool_version, normalize_config(config), schema_version]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JobManifest:
    """一次媒体操作的可重放记录（输入哈希 + 工具版本 + 输出哈希）。"""

    op: str  # 操作名，如 media.proxy.ffmpeg / media.audio.ffmpeg / media.scene.ffmpeg
    schema_version: str
    inputs: tuple[str, ...]  # 输入 artifact 的 sha256（可多输入）
    tool: str  # ffmpeg / ffprobe
    tool_version: str
    config: dict[str, Any]  # 规范化前的操作配置（原始 dict）
    outputs: tuple[str, ...] = ()  # 输出 artifact 的 sha256（分析型操作可为空）
    created_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)  # wall_ms 等（可选）

    @property
    def cache_key(self) -> str:
        """本操作的 Activity Cache Key（以首个输入为 input_digest）。"""
        primary = self.inputs[0] if self.inputs else ""
        return activity_cache_key(
            input_digest=primary,
            provider=self.op,
            tool_version=self.tool_version,
            config=self.config,
            schema_version=self.schema_version,
        )
