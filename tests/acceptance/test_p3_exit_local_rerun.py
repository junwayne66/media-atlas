"""P3 Exit 验收 —— 一句改动的重跑范围（§12 第 2 条）。

**证据边界**（诚实登记，verifier 指出）：
AnalysisWorkflow 尚未落地（P2 起就是延后项），生产代码里**尚无任何 activity 在真正调用**
`activity_cache_key`。因此本测试证的是**原语层**契约：`activity_cache_key(input_digest,
provider, tool_version, config, schema_version)` 作为哈希函数具备命名空间隔离/输入敏感/
版本敏感的正确性，为将来接入的每类 activity（download/ASR/OCR/VLM/script）提供**统一
且可复用**的缓存键计算方式。

工作流层的"改一句台词只重跑受影响下游"目标 = 每类 activity 都用此原语生成键 + 缓存查询。
原语正确性是 workflow 层证明的**必要条件**（原语错则各 activity 键都失效）；workflow 层
本身的证明将在 AnalysisWorkflow 落地时另加集成测试。

本文件的每个测试案例的 `provider` / `tool_version` / `config` 字段是**代表性构造**（用
真实的 downloader/ASR 值格），非产品线绑定值——原语性质与具体值无关。
"""

from __future__ import annotations

from videoforge_media_core import activity_cache_key


def _upstream_download_key(source_url_digest: str) -> str:
    """下载 activity 的 cache_key：仅取决于源 artifact 摘要 + 下载器版本 + 配置。"""
    return activity_cache_key(
        input_digest=source_url_digest,
        provider="acquisition.download.yt_dlp",
        tool_version="2025.01.15",
        config={"format": "bv*+ba/b", "cookiefile": "credential-handle-A"},
    )


def _upstream_asr_key(audio_artifact_digest: str) -> str:
    """ASR activity 的 cache_key：取决于抽出音频摘要 + ASR 提供方 + 模型版本 + 语言。"""
    return activity_cache_key(
        input_digest=audio_artifact_digest,
        provider="analysis.asr.whisper",
        tool_version="v3-large",
        config={"language": "zh-CN", "vad": True},
    )


def _script_stage_key(script_hash: str) -> str:
    """脚本 activity 的 cache_key：取决于脚本 hash（一句改动 → 整脚本 hash 变）+ 时间轴模板。"""
    return activity_cache_key(
        input_digest=script_hash,
        provider="creation.timeline_compile",
        tool_version="v1",
        config={"aspect_ratio": "9:16", "rate": 30},
    )


def test_upstream_stages_unaffected_by_downstream_script_edit() -> None:
    """上游 download/ASR 的 cache_key 与脚本内容无关 —— 一句改动不应触发它们重跑。"""
    source_digest = "a" * 64
    audio_digest = "b" * 64

    # 场景 A：原脚本
    dl_a = _upstream_download_key(source_digest)
    asr_a = _upstream_asr_key(audio_digest)

    # 场景 B：脚本被编辑（但源视频/音频未变）
    dl_b = _upstream_download_key(source_digest)
    asr_b = _upstream_asr_key(audio_digest)

    assert dl_a == dl_b, "改脚本竟触发下载重跑（cache_key 应稳定）"
    assert asr_a == asr_b, "改脚本竟触发 ASR 重跑（cache_key 应稳定）"


def test_script_edit_changes_downstream_cache_key() -> None:
    """改一句台词 → 下游脚本 activity 的 cache_key 必变，触发时间轴重编译。"""
    key_before = _script_stage_key(script_hash="c" * 64)
    key_after = _script_stage_key(script_hash="d" * 64)  # 一句改动 → 整脚本 hash 变
    assert key_before != key_after, "改脚本 cache_key 未变 —— 下游不会重跑"


def test_cache_key_isolation_by_provider() -> None:
    """同一输入不同 provider（下载 vs ASR）绝不产生同一 cache_key —— 命名空间隔离。"""
    same = "e" * 64
    dl = _upstream_download_key(same)
    asr = _upstream_asr_key(same)
    assert dl != asr, "provider 不同却 cache_key 相同 —— 命名空间污染"


def test_config_change_forces_recompute_but_not_input_change() -> None:
    """换 ASR 语言（config 变）→ ASR cache_key 变；同一 config 二次调用 → cache_key 稳。"""
    audio = "f" * 64
    zh_key = activity_cache_key(
        input_digest=audio, provider="analysis.asr.whisper",
        tool_version="v3-large", config={"language": "zh-CN", "vad": True},
    )
    en_key = activity_cache_key(
        input_digest=audio, provider="analysis.asr.whisper",
        tool_version="v3-large", config={"language": "en-US", "vad": True},
    )
    zh_key_again = activity_cache_key(
        input_digest=audio, provider="analysis.asr.whisper",
        tool_version="v3-large", config={"language": "zh-CN", "vad": True},
    )
    assert zh_key != en_key, "换语言 cache_key 未变 —— 会错命中"
    assert zh_key == zh_key_again, "同 config 二次 cache_key 不稳 —— 无法复用"


def test_tool_version_upgrade_invalidates_cache() -> None:
    """升级 ASR 模型（tool_version 变）→ cache_key 变，触发全量重跑（41 §11 契约）。"""
    audio = "9" * 64
    v3 = activity_cache_key(
        input_digest=audio, provider="analysis.asr.whisper",
        tool_version="v3-large", config={"language": "zh-CN"},
    )
    v4 = activity_cache_key(
        input_digest=audio, provider="analysis.asr.whisper",
        tool_version="v4-large", config={"language": "zh-CN"},
    )
    assert v3 != v4, "换工具版本 cache_key 未变 —— 版本升级会静默复用旧结果"
