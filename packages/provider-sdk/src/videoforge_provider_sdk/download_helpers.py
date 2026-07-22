"""下载连接器共用辅助（安全关键，单实现单测试，避免各连接器各写一份而分叉）。

- scrub_metadata：递归剔除机密键——info-dict 常含 http_headers.Cookie / 鉴权头 /
  token；返回给上层的诊断元数据绝不带明文凭据（README §4）。
- sha256_file：流式哈希，产出可重放 manifest 的 output 哈希。
- locate_downloaded_media：从 info-dict 定位产物，且**约束在 dest_dir 内**——不信任
  info-dict 给的越界绝对路径（纵深防御）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# raw_metadata 里必须抹掉的机密键（子串匹配，递归）
_SENSITIVE_KEY_MARKERS = (
    "cookie",
    "authorization",
    "token",
    "password",
    "credential",
    "secret",
    "http_headers",
)


def scrub_metadata(obj: Any) -> Any:
    """递归剔除机密键——info-dict 常含 http_headers.Cookie / 各格式的鉴权头。"""
    if isinstance(obj, dict):
        return {
            k: scrub_metadata(v)
            for k, v in obj.items()
            if not any(m in str(k).lower() for m in _SENSITIVE_KEY_MARKERS)
        }
    if isinstance(obj, list):
        return [scrub_metadata(v) for v in obj]
    return obj


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def locate_downloaded_media(dest_dir: Path, info: dict[str, Any]) -> Path | None:
    """从 info-dict 定位下载产物；产物必须落在 dest_dir 内（拒绝越界绝对路径）。"""
    candidates: list[str | None] = []
    downloads = info.get("requested_downloads")
    if isinstance(downloads, list) and downloads and isinstance(downloads[0], dict):
        candidates.append(downloads[0].get("filepath"))
    candidates.extend([info.get("filepath"), info.get("_filename")])
    vid, ext = info.get("id"), info.get("ext")
    if vid and ext:
        candidates.append(f"{vid}.{ext}")

    dest = dest_dir.resolve()
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand)
        p = p if p.is_absolute() else dest_dir / p.name
        try:
            p.resolve().relative_to(dest)  # 纵深防御：拒绝 dest_dir 外的路径
        except ValueError:
            continue
        if p.is_file():
            return p
    return None
