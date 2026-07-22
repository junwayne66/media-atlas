"""f2 执行后端：连接器只构造 args 数组，把「跑子进程」隔离到 runner（同 yt-dlp 范式）。

- UnconfiguredF2Runner：默认。实时下载未启用（需真实 f2 二进制 + 真实资源，53 §10 停止条件）
  ——返回 UNCONFIGURED，绝不静默假成功。
- SubprocessF2Runner：真实路径。参数数组子进程调用（禁 shell 字符串），须显式二进制，版本探测。
  测试从不构造它——单元测试不触网。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from videoforge_provider_sdk import AcquisitionError, AcquisitionErrorCode

# 版本锁定（descriptor.yaml 同步）：升级须重跑连接器契约测试并复核提取路径
PINNED_VERSION = "0.0.1.7"


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


class F2Runner(Protocol):
    version: str

    def run(self, argv: list[str], *, timeout_s: int) -> RunResult:
        """执行 f2（argv 不含二进制自身）；不抛下载错误，由连接器读 returncode/stderr 映射。"""
        ...


class F2NotAvailable(RuntimeError):
    pass


class UnconfiguredF2Runner:
    """默认后端：实时下载未启用。"""

    version = "unconfigured"

    def __init__(self, detail: str | None = None) -> None:
        self._detail = detail or (
            "实时下载未启用：需安装 f2 二进制并显式授权（真实资源/账号，停止条件）；"
            "此前请用 yt-dlp 回退或手工导入本地原片"
        )

    def run(self, argv: list[str], *, timeout_s: int) -> RunResult:
        raise AcquisitionError(AcquisitionErrorCode.UNCONFIGURED, self._detail)


class SubprocessF2Runner:
    """真实后端：args-array 子进程执行 f2，禁 shell 字符串。须显式二进制。"""

    def __init__(self, binary: str | None = None) -> None:
        resolved = binary or shutil.which("f2")
        if resolved is None:
            raise F2NotAvailable("找不到 f2；请安装并锁定版本，或显式传入路径")
        self._binary = resolved
        self.version = self._probe_version()

    def _probe_version(self) -> str:
        result = subprocess.run(
            [self._binary, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return result.stdout.strip()

    def run(self, argv: list[str], *, timeout_s: int) -> RunResult:
        # 参数数组执行：每个元素独立传入，绝不拼接为 shell 字符串（无注入面）
        result = subprocess.run(
            [self._binary, *argv],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return RunResult(result.returncode, result.stdout, result.stderr)
