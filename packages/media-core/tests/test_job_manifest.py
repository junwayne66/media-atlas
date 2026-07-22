"""Job Manifest + Activity Cache Key：可重放、规范化、任一因子变化即换 key（41 §11）。"""

from datetime import UTC, datetime

from videoforge_media_core.job_manifest import (
    MANIFEST_SCHEMA_VERSION,
    JobManifest,
    activity_cache_key,
    normalize_config,
)

_BASE = dict(
    input_digest="a" * 64,
    provider="media.proxy.ffmpeg",
    tool_version="8.1.2",
    config={"height": 720, "crf": 28},
)


def test_cache_key_is_deterministic() -> None:
    assert activity_cache_key(**_BASE) == activity_cache_key(**_BASE)
    assert len(activity_cache_key(**_BASE)) == 64


def test_cache_key_changes_with_each_factor() -> None:
    base = activity_cache_key(**_BASE)
    assert activity_cache_key(**{**_BASE, "input_digest": "b" * 64}) != base
    assert activity_cache_key(**{**_BASE, "provider": "media.audio.ffmpeg"}) != base
    assert activity_cache_key(**{**_BASE, "tool_version": "7.1"}) != base
    assert activity_cache_key(**{**_BASE, "config": {"height": 480, "crf": 28}}) != base
    assert activity_cache_key(**{**_BASE, "schema_version": "2.0"}) != base


def test_normalize_config_is_key_order_independent() -> None:
    assert normalize_config({"a": 1, "b": 2}) == normalize_config({"b": 2, "a": 1})
    # 配置相同（键序不同）→ cache key 相同
    k1 = activity_cache_key(**{**_BASE, "config": {"crf": 28, "height": 720}})
    k2 = activity_cache_key(**{**_BASE, "config": {"height": 720, "crf": 28}})
    assert k1 == k2


def test_manifest_cache_key_uses_first_input_and_config() -> None:
    m = JobManifest(
        op="media.proxy.ffmpeg",
        schema_version=MANIFEST_SCHEMA_VERSION,
        inputs=("a" * 64,),
        tool="ffmpeg",
        tool_version="8.1.2",
        config={"height": 720, "crf": 28},
        outputs=("c" * 64,),
        created_at=datetime.now(UTC),
    )
    assert m.cache_key == activity_cache_key(
        input_digest="a" * 64,
        provider="media.proxy.ffmpeg",
        tool_version="8.1.2",
        config={"height": 720, "crf": 28},
    )
    # 输出哈希不参与 cache key（同输入同配置即命中，与本次输出无关）
    m2 = JobManifest(
        op="media.proxy.ffmpeg",
        schema_version=MANIFEST_SCHEMA_VERSION,
        inputs=("a" * 64,),
        tool="ffmpeg",
        tool_version="8.1.2",
        config={"height": 720, "crf": 28},
        outputs=("d" * 64,),
        created_at=datetime.now(UTC),
    )
    assert m.cache_key == m2.cache_key
