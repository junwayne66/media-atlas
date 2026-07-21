"""descriptor.yaml → ProviderDescriptor 合同（52 §3：descriptor 声明能力、
版本、限流、许可证和所需 Secret）。加载即校验，非法描述文件立即报错。"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from videoforge_contracts import ProviderDescriptor


class DescriptorError(Exception):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path


def load_descriptor(path: Path) -> ProviderDescriptor:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DescriptorError(path, f"YAML 解析失败: {exc}") from exc
    if not isinstance(raw, dict):
        raise DescriptorError(path, "描述文件必须是映射结构")
    try:
        return ProviderDescriptor.model_validate(raw)
    except ValidationError as exc:
        raise DescriptorError(path, f"不符合 ProviderDescriptor 合同: {exc}") from exc


def scan_descriptors(root: Path) -> list[ProviderDescriptor]:
    """递归收集 root 下所有 descriptor.yaml，按 name 排序返回。"""
    found = [load_descriptor(p) for p in sorted(root.rglob("descriptor.yaml"))]
    names = [d.name for d in found]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise DescriptorError(root, f"descriptor 名称重复: {sorted(duplicates)}")
    return sorted(found, key=lambda d: d.name)
