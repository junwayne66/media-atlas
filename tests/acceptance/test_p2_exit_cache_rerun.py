"""P2 Exit 验收（局部重跑）：Activity Cache Key 命中不重复计算/下载（docs/modules/41 §11）。

53 §P2 Exit：「局部 Provider 重跑不重复下载」。用 VF-201 的 activity_cache_key 把一个计数
Provider 包成 CachedStage：同 input+provider+model_version+config 重跑命中缓存、不再调用底层；
改任一因子即未命中、重算。据此换字幕不重跑下载/镜头、换 OCR 模型只重跑 OCR。
"""

from videoforge_media_core import activity_cache_key


class _CountingProvider:
    """底层 Provider：每次真正执行都计数（代表下载/转码/OCR 等昂贵操作）。"""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, input_digest: str, config: dict) -> str:
        self.calls += 1
        return f"result::{input_digest}::{sorted(config.items())}"


class _CachedStage:
    """按 Activity Cache Key 缓存：命中直接返回，未命中才调用底层 Provider。"""

    def __init__(self, provider: _CountingProvider, *, name: str, model_version: str) -> None:
        self._provider = provider
        self._name = name
        self._version = model_version
        self._cache: dict[str, str] = {}

    def run(self, input_digest: str, config: dict) -> str:
        key = activity_cache_key(
            input_digest=input_digest,
            provider=self._name,
            tool_version=self._version,
            config=config,
        )
        if key in self._cache:
            return self._cache[key]  # 命中：不调用底层（不重复下载/计算）
        result = self._provider.run(input_digest, config)
        self._cache[key] = result
        return result


def test_rerun_same_input_hits_cache_no_recompute() -> None:
    prov = _CountingProvider()
    stage = _CachedStage(prov, name="media.download.yt_dlp", model_version="yt-dlp@2025.01.15")
    a = stage.run("sha-A", {"format": "best"})
    b = stage.run("sha-A", {"format": "best"})  # 局部重跑
    assert a == b
    assert prov.calls == 1  # 命中缓存，底层只执行一次（不重复下载）


def test_changed_config_recomputes() -> None:
    prov = _CountingProvider()
    stage = _CachedStage(prov, name="media.proxy.ffmpeg", model_version="ffmpeg@8.1.2")
    stage.run("sha-A", {"height": 720})
    stage.run("sha-A", {"height": 480})  # 配置变 → 未命中
    assert prov.calls == 2


def test_changed_model_version_yields_different_key() -> None:
    # 换 OCR 模型 → 不同缓存键 → 不命中旧缓存，只重跑该阶段（换 OCR 模型只重跑 OCR）
    base = dict(input_digest="sha-A", provider="ocr.paddle", config={})
    assert activity_cache_key(tool_version="2.7", **base) != activity_cache_key(
        tool_version="3.0", **base
    )
    # 同输入同模型同配置 → 同键（可重放/命中）
    assert activity_cache_key(tool_version="2.7", **base) == activity_cache_key(
        tool_version="2.7", **base
    )


def test_different_input_recomputes() -> None:
    prov = _CountingProvider()
    stage = _CachedStage(prov, name="asr.whisperx", model_version="large-v3")
    stage.run("sha-A", {})
    stage.run("sha-B", {})  # 不同输入（换了源）→ 重算
    assert prov.calls == 2


def test_cache_key_config_order_independent() -> None:
    # 配置键序不影响缓存键（规范化）→ 语义相同的配置命中同一缓存
    prov = _CountingProvider()
    stage = _CachedStage(prov, name="s", model_version="v")
    stage.run("sha-A", {"a": 1, "b": 2})
    stage.run("sha-A", {"b": 2, "a": 1})  # 键序不同、语义相同
    assert prov.calls == 1
