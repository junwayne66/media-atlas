"""测试辅助：回放录制 yt-dlp 行为，全程不触网（basename 唯一，避开 pytest 顶层冲突）。

FixtureYtDlpRunner 模拟真实 runner 契约：成功时把假媒体字节写到 argv 指定的输出目录
（--paths=home:<dir> + id.ext），并在 stdout 回放 info-dict；失败时回放 returncode/stderr。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoforge_connector_yt_dlp import RunResult

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_info_dict() -> dict[str, Any]:
    return json.loads((_FIXTURES / "info_dict.json").read_text(encoding="utf-8"))


def _paths_home(argv: list[str]) -> Path | None:
    for token in argv:
        if token.startswith("--paths=home:"):
            return Path(token[len("--paths=home:") :])
    return None


class FixtureYtDlpRunner:
    """回放录制响应；成功路径会真的写出一个小文件供连接器哈希。"""

    def __init__(
        self,
        info: dict[str, Any] | None = None,
        *,
        media_bytes: bytes = b"FAKEMEDIA",
        returncode: int = 0,
        stderr: str = "",
        version: str = "2025.01.15",
    ) -> None:
        self._info = info if info is not None else load_info_dict()
        self._media = media_bytes
        self._returncode = returncode
        self._stderr = stderr
        self.version = version
        self.calls: list[list[str]] = []  # 记录每次 argv，便于断言

    def run(self, argv: list[str], *, timeout_s: int) -> RunResult:
        self.calls.append(list(argv))
        if self._returncode != 0:
            return RunResult(self._returncode, "", self._stderr)
        if "--skip-download" not in argv:
            dest = _paths_home(argv)
            if dest is not None:
                dest.mkdir(parents=True, exist_ok=True)
                target = dest / f"{self._info['id']}.{self._info['ext']}"
                if not target.exists():  # 幂等：已存在不覆盖（模拟 --no-overwrites）
                    target.write_bytes(self._media)
        return RunResult(0, json.dumps(self._info), "")
