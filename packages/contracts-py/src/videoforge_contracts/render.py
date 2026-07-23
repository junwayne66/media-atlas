"""渲染合同（docs/modules/42 §8.3）。

非协商规则（docs/README §4）：**FFmpeg 只以参数数组调用，绝不 shell 拼接**；输入路径受白名单
约束；每次渲染产出可复现的 RenderManifest（输入哈希 + 工具版本 + 输出哈希）。本模块把这三条纪律
落到类型系统里——凡是"渲染指令"都走 list[str]、任何元素含 shell 元字符即在合同层被拒绝。

Filter Graph 建模为节点 + 边的 DAG（不是拼好的字符串）；序列化为 ffmpeg -filter_complex 由 domain
编译器负责。分层严格：本合同族只描述"要渲染成什么"，实际调用 ffmpeg 与磁盘 I/O 在 media-core。
"""

import re
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import RenderStage, RenderTargetKind

# 严禁出现在 argv 元素中的 shell 元字符——即便 argv 不走 shell，本层做纵深防御：
# 阻止意外通过 python-shlex 或第三方模块被误解释；也让审计更简单。
_SHELL_META_CHARS = frozenset(";|&<>`$\\\"'\n\r\t")
# 稍宽松：允许滤镜参数中的 = 与 :（ffmpeg 语法），但不允许换行/引号/管道等控制字符
_FILTER_PARAM_META = frozenset(";|&<>`$\\\"'\n\r\t")
# 允许的 argv 空白：单空格不允许，但特定标志如 -y/-hide_banner 无空白；参数值若含空白必须走单独元素
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _reject_shell_metachars(value: str, forbidden: frozenset[str]) -> str:
    if any(c in forbidden for c in value):
        offenders = sorted({c for c in value if c in forbidden})
        raise ValueError(
            f"含不允许的 shell 元字符 {offenders!r}；argv 必须为纯 token（无 shell 拼接）"
        )
    return value


class RenderInput(ContractModel):
    """一个渲染输入：素材身份 + 内容哈希 + 已解析的绝对路径（须在白名单内，由 domain 校验）。"""

    asset_id: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64, description="内容哈希，可复现验证")
    resolved_path: str = Field(min_length=1, description="已解析的绝对路径")
    role: str | None = Field(default=None, description="video/audio/subtitle/…")

    @field_validator("sha256")
    @classmethod
    def _hex_sha256(cls, v: str) -> str:
        if not _SHA256_RE.match(v):
            raise ValueError("sha256 必须是 64 位小写十六进制")
        return v

    @field_validator("resolved_path")
    @classmethod
    def _no_shell_metachars(cls, v: str) -> str:
        return _reject_shell_metachars(v, _SHELL_META_CHARS)


class FilterNode(ContractModel):
    """Filter Graph 单节点：滤镜名 + 参数字典 + 输入/输出标签。参数值受元字符拒绝。"""

    id: str = Field(min_length=1)
    filter: str = Field(min_length=1, description="ffmpeg 滤镜名，如 trim/setpts/scale/overlay")
    params: dict[str, str] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list, description="上游节点/输入流标签")
    outputs: list[str] = Field(min_length=1, description="本节点产出的标签")

    @field_validator("filter")
    @classmethod
    def _filter_name_safe(cls, v: str) -> str:
        # 滤镜名限定为字母/数字/下划线，堵 filter injection
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", v):
            raise ValueError(f"滤镜名 {v!r} 含非法字符；仅允许 [a-zA-Z_0-9]，首字符字母")
        return v

    @field_validator("params")
    @classmethod
    def _params_no_metachars(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            _reject_shell_metachars(key, _FILTER_PARAM_META)
            _reject_shell_metachars(val, _FILTER_PARAM_META)
        return v


class FilterGraph(ContractModel):
    """Filter Graph DAG：节点集合 + 边由 inputs/outputs 隐式定义。禁循环（domain 层拓扑校验）。"""

    nodes: list[FilterNode] = Field(default_factory=list)
    sinks: list[str] = Field(default_factory=list, description="终点标签，供 -map 引用")

    @model_validator(mode="after")
    def _unique_output_labels(self) -> "FilterGraph":
        seen: set[str] = set()
        for node in self.nodes:
            for label in node.outputs:
                if label in seen:
                    raise ValueError(f"重复的滤镜输出标签 {label!r}")
                seen.add(label)
        return self


class FfmpegRenderGraph(ContractModel):
    """FFmpeg 渲染指令：严格 argv 数组 + Filter Graph + 版本 pin。**绝不 shell 拼接**。"""

    args: list[str] = Field(min_length=1, description="ffmpeg argv，绝无 shell 拼接")
    filter_complex: FilterGraph | None = None
    inputs: list[RenderInput] = Field(default_factory=list)
    output_path: str = Field(min_length=1, description="输出绝对路径")
    target: RenderTargetKind
    tool_version: str = Field(min_length=1, description="ffmpeg 版本，供复现")

    @field_validator("args")
    @classmethod
    def _argv_safe(cls, v: list[str]) -> list[str]:
        for i, token in enumerate(v):
            if not token:
                raise ValueError(f"args[{i}] 为空 token；每个 argv 元素须非空")
            _reject_shell_metachars(token, _SHELL_META_CHARS)
        return v

    @field_validator("output_path")
    @classmethod
    def _output_path_safe(cls, v: str) -> str:
        return _reject_shell_metachars(v, _SHELL_META_CHARS)


class RenderManifest(ContractModel):
    """一次渲染的可复现清单（§8.3）：输入哈希 + 工具版本 + 输出哈希 + 时间线来源。"""

    id: str = Field(min_length=1)
    timeline_id: str = Field(min_length=1, description="源 CreativeTimeline id")
    stage: RenderStage
    render_graph: FfmpegRenderGraph
    input_digests: dict[str, str] = Field(
        default_factory=dict, description="{asset_id: sha256} 供缓存与重放"
    )
    output_digest: str | None = Field(
        default=None, min_length=64, max_length=64, description="产出内容 sha256；未渲染前为 null"
    )
    duration_ms: int | None = Field(default=None, ge=0)
    tool_version: str = Field(min_length=1)
    created_at: datetime

    @field_validator("input_digests")
    @classmethod
    def _digests_hex(cls, v: dict[str, str]) -> dict[str, str]:
        for aid, digest in v.items():
            if not _SHA256_RE.match(digest):
                raise ValueError(f"input_digests[{aid}] 非法 sha256")
        return v

    @field_validator("output_digest")
    @classmethod
    def _output_digest_hex(cls, v: str | None) -> str | None:
        if v is not None and not _SHA256_RE.match(v):
            raise ValueError("output_digest 必须是 64 位小写十六进制")
        return v
