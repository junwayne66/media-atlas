"""工具链探测：记录实际二进制路径与版本，不假定 PATH 语义（50 §10）。

自检结果以 Capability 上报（55 §5），后续 ToolchainRegistry 任务补充
buildconf 与校验和。
"""

import re
import shutil
import subprocess


def _probe_binary(name: str) -> dict[str, str] | None:
    path = shutil.which(name)
    if path is None:
        return None
    try:
        result = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=10, check=True
        )
    except (subprocess.SubprocessError, OSError):
        return {"path": path, "version": "unknown"}
    match = re.search(r"version\s+(\S+)", result.stdout)
    return {"path": path, "version": match.group(1) if match else "unknown"}


def probe_toolchain() -> dict[str, dict[str, str] | None]:
    return {name: _probe_binary(name) for name in ("ffmpeg", "ffprobe")}
