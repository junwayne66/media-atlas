from pathlib import Path

import pytest

from videoforge_provider_sdk import DescriptorError, load_descriptor, scan_descriptors

REPO_ROOT = Path(__file__).parents[3]


def test_loads_repo_fake_descriptors() -> None:
    found = scan_descriptors(REPO_ROOT / "connectors")
    names = [d.name for d in found]
    assert "source.fake" in names
    assert "render.fake" in names
    source = next(d for d in found if d.name == "source.fake")
    assert source.platforms == ["douyin", "tiktok"]
    assert "source.discover" in source.capabilities


def test_invalid_descriptor_rejected(tmp_path) -> None:
    bad = tmp_path / "descriptor.yaml"
    bad.write_text("name: x\nprovider_type: ASRProvider\n", encoding="utf-8")  # 缺必填字段
    with pytest.raises(DescriptorError, match="不符合 ProviderDescriptor 合同"):
        load_descriptor(bad)


def test_non_mapping_descriptor_rejected(tmp_path) -> None:
    bad = tmp_path / "descriptor.yaml"
    bad.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(DescriptorError, match="映射结构"):
        load_descriptor(bad)


def test_duplicate_names_rejected(tmp_path) -> None:
    for sub in ("a", "b"):
        d = tmp_path / sub
        d.mkdir()
        (d / "descriptor.yaml").write_text(
            "name: dup.fake\nprovider_type: ASRProvider\nversion: '1'\n"
            "capabilities: [x]\nexecution_location: local\n",
            encoding="utf-8",
        )
    with pytest.raises(DescriptorError, match="重复"):
        scan_descriptors(tmp_path)
