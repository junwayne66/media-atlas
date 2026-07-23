"""Remotion 渲染合同（docs/modules/42 §8.3；ADR-002 Remotion 特殊许可）。

**许可提示**：Remotion 商业授权对使用者有条款要求，需专项评审。本模块**只描述"要渲染成什么"**，
不集成 Remotion 运行时；渲染由独立 RenderProvider 端口后置隔离，真实调用延后至许可评审通过。

合同层与 VF-307 FFmpeg Compiler 一致的纵深防御：
- 所有字符串值（entry_component_path、Prop.value 中的 str 分支）均拒 shell 元字符；
- 数字/布尔/列表/字典嵌套值层层校验；
- `entry_component_path` 由 domain 强制在白名单目录内（`_path_within` 复用 VF-307）；
- RemotionRenderManifest 复用 §11 cache key 公式，供缓存与复现。
"""

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import RemotionComposition

# 与 VF-307 render.py 同一套 shell 元字符禁令——纵深防御
_SHELL_META_CHARS = frozenset(";|&<>`$\\\"'\n\r\t")

# 允许在 Prop 值中出现的最深嵌套（防指数爆炸/递归攻击）
_MAX_PROP_DEPTH = 8
# Prop 值允许的原子类型（JSON 兼容）
_PropAtom = str | int | float | bool | None


def _reject_shell_metachars(value: str, field: str) -> str:
    if any(c in _SHELL_META_CHARS for c in value):
        offenders = sorted({c for c in value if c in _SHELL_META_CHARS})
        raise ValueError(
            f"{field} 含不允许的 shell 元字符 {offenders!r}；纵深防御"
        )
    return value


def _validate_prop_value(value: Any, path: str, depth: int) -> Any:
    """递归校验 Prop 值：允许 JSON 兼容原子/列表/字典；字符串拒 shell 元字符；限深防炸。"""
    if depth > _MAX_PROP_DEPTH:
        raise ValueError(f"prop 值嵌套深度超过 {_MAX_PROP_DEPTH} at {path}")
    if isinstance(value, bool):  # bool 优先于 int（isinstance 顺序）
        return value
    if value is None or isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return _reject_shell_metachars(value, f"prop {path}")
    if isinstance(value, list):
        return [_validate_prop_value(v, f"{path}[{i}]", depth + 1) for i, v in enumerate(value)]
    if isinstance(value, dict):
        for k in value.keys():
            if not isinstance(k, str):
                raise ValueError(f"prop dict 键必须是字符串 at {path}, got {type(k)}")
            _reject_shell_metachars(k, f"prop {path} 键")
        return {k: _validate_prop_value(v, f"{path}.{k}", depth + 1) for k, v in value.items()}
    raise ValueError(f"prop 值类型不支持 at {path}: {type(value)}")


class RemotionProp(ContractModel):
    """单个类型化 Prop——Remotion React 组件将以此消费。value 层层校验，禁 shell 元字符渗入。"""

    key: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
                     description="组件 Prop 键；限 JS 标识符规则")
    value: Any = Field(description="JSON 兼容值；str/int/float/bool/None/list/dict 递归校验")

    @field_validator("value")
    @classmethod
    def _validate_value(cls, v: Any) -> Any:
        return _validate_prop_value(v, path="root", depth=0)


class RemotionRenderRequest(ContractModel):
    """一次 Remotion 渲染请求：组件 + Props + 时长 + 帧率 + 分辨率 + 组件入口路径。"""

    id: str = Field(min_length=1)
    timeline_id: str = Field(min_length=1, description="源 CreativeTimeline id")
    composition: RemotionComposition
    props: list[RemotionProp] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)
    fps: int = Field(gt=0, le=120, description="≤120 fps 满足绝大多数场景")
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)
    entry_component_path: str = Field(
        min_length=1, description="Remotion Root React 组件路径，须落在白名单内（domain 强制）"
    )
    output_path: str = Field(min_length=1, description="渲染输出路径，须落在白名单内")
    tool_version: str = Field(min_length=1, description="Remotion CLI/npm 版本，供复现")

    @field_validator("entry_component_path", "output_path")
    @classmethod
    def _no_shell_metachars(cls, v: str) -> str:
        return _reject_shell_metachars(v, "path")

    @model_validator(mode="after")
    def _unique_prop_keys(self) -> "RemotionRenderRequest":
        keys = [p.key for p in self.props]
        if len(keys) != len(set(keys)):
            raise ValueError("props 键重复")
        return self


class RemotionRenderManifest(ContractModel):
    """一次 Remotion 渲染的可复现清单（§8.3；对齐 VF-307 RenderManifest 语义）。"""

    id: str = Field(min_length=1)
    request: RemotionRenderRequest
    input_digests: dict[str, str] = Field(
        default_factory=dict, description="{asset_id: sha256} 供缓存与重放"
    )
    output_digest: str | None = Field(
        default=None, min_length=64, max_length=64,
        description="产出内容 sha256；未渲染前为 null",
    )
    tool_version: str = Field(min_length=1)
    created_at: datetime

    @field_validator("input_digests")
    @classmethod
    def _digests_hex(cls, v: dict[str, str]) -> dict[str, str]:
        import re
        pat = re.compile(r"^[0-9a-f]{64}$")
        for aid, digest in v.items():
            if not pat.match(digest):
                raise ValueError(f"input_digests[{aid}] 非法 sha256")
        return v

    @field_validator("output_digest")
    @classmethod
    def _output_digest_hex(cls, v: str | None) -> str | None:
        if v is not None:
            import re
            if not re.fullmatch(r"^[0-9a-f]{64}$", v):
                raise ValueError("output_digest 必须是 64 位小写十六进制")
        return v
