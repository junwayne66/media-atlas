"""VF-407 provider-sdk 一致性：Unconfigured / Fake 浅层专名检查 / 零重导入。"""

import ast
import inspect

import videoforge_provider_sdk.localization_review as consistency_module
from videoforge_contracts import LocalizationQACheck, QASeverity
from videoforge_provider_sdk import (
    ConsistencyCheckRequest,
    ConsistencyErrorCode,
    ConsistencyStatus,
    FakeLocalizationConsistencyProvider,
    LocalizationConsistencyProvider,
    UnconfiguredLocalizationConsistencyProvider,
)


def _req(target: str, entities: tuple[str, ...]) -> ConsistencyCheckRequest:
    return ConsistencyCheckRequest(
        sentence_id="s",
        source="Apple M5 chip",
        target=target,
        source_lang="en-US",
        target_lang="zh-CN",
        source_entities=entities,
    )


def test_providers_satisfy_protocol():
    assert isinstance(FakeLocalizationConsistencyProvider(), LocalizationConsistencyProvider)
    assert isinstance(
        UnconfiguredLocalizationConsistencyProvider(),
        LocalizationConsistencyProvider,
    )


def test_unconfigured_returns_unconfigured_no_findings():
    r = UnconfiguredLocalizationConsistencyProvider().check(_req("苹果 M5", ("Apple", "M5")))
    assert r.status is ConsistencyStatus.UNCONFIGURED
    assert r.findings == []
    assert r.error_code is ConsistencyErrorCode.ENGINE_UNAVAILABLE


def test_fake_flags_missing_proper_noun():
    r = FakeLocalizationConsistencyProvider().check(_req("M5 芯片", ("Apple", "M5")))
    assert r.status is ConsistencyStatus.OK
    # Apple 未出现在译文 → 一条 MAJOR PROPER_NOUN 发现；M5 出现 → 不报
    assert len(r.findings) == 1
    f = r.findings[0]
    assert f.check is LocalizationQACheck.PROPER_NOUN_CONSISTENCY
    assert f.severity is QASeverity.MAJOR
    assert f.evidence["entity"] == "Apple"


def test_fake_no_findings_when_all_entities_present():
    r = FakeLocalizationConsistencyProvider().check(_req("Apple M5 芯片", ("Apple", "M5")))
    assert r.findings == []


def test_fake_is_case_insensitive():
    r = FakeLocalizationConsistencyProvider().check(_req("apple m5", ("Apple", "M5")))
    assert r.findings == []


def test_fake_warns_about_shallow_check():
    r = FakeLocalizationConsistencyProvider().check(_req("M5", ("M5",)))
    assert any("浅层" in w or "深层" in w for w in r.warnings)


def test_fake_is_deterministic_and_deep_copies():
    p = FakeLocalizationConsistencyProvider()
    req = _req("M5 芯片", ("Apple", "M5"))
    a = p.check(req)
    b = p.check(req)
    assert [f.evidence["entity"] for f in a.findings] == [f.evidence["entity"] for f in b.findings]
    assert req.target == "M5 芯片"  # 输入未被改动


def test_module_has_zero_heavy_imports():
    tree = ast.parse(inspect.getsource(consistency_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {
        "__future__",
        "copy",
        "dataclasses",
        "enum",
        "typing",
        "videoforge_contracts",
    }
    assert imported <= allowed, f"引入非白名单模块: {imported - allowed}"
