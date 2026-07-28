"""真实网络适配器使用的 SSRF/重定向目标策略（VF-108）。

本模块只做目标判定，不发 HTTP 请求。测试注入 resolver，因此完全离线；未来 live adapter
必须在首跳和每次 redirect 前调用同一策略。
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

HostResolver = Callable[[str], Iterable[str]]


class UnsafeNetworkTarget(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedNetworkTarget:
    url: str
    host: str
    addresses: tuple[str, ...]


def system_resolver(host: str) -> list[str]:
    return sorted({entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


def validate_url_target(
    url: str,
    *,
    allowed_hosts: set[str] | frozenset[str],
    resolver: HostResolver = system_resolver,
) -> ValidatedNetworkTarget:
    if any(ord(char) < 32 for char in url) or "\\" in url:
        raise UnsafeNetworkTarget("URL 含控制字符或反斜杠")
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise UnsafeNetworkTarget("只允许 HTTPS 目标")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeNetworkTarget("URL 禁止 userinfo")
    if "%" in parsed.netloc:
        raise UnsafeNetworkTarget("URL host 禁止百分号编码")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeNetworkTarget("URL 端口非法") from exc
    if port not in {None, 443}:
        raise UnsafeNetworkTarget("只允许默认 HTTPS 端口")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host or host not in allowed_hosts:
        raise UnsafeNetworkTarget(f"host 不在 allowlist: {host or '<empty>'}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeNetworkTarget("禁止 IP literal")

    addresses = tuple(dict.fromkeys(resolver(host)))
    if not addresses:
        raise UnsafeNetworkTarget("DNS 未返回地址")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise UnsafeNetworkTarget(f"DNS 返回非法地址: {raw}") from exc
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise UnsafeNetworkTarget(f"DNS 目标不是公网地址: {raw}")
    return ValidatedNetworkTarget(url=url, host=host, addresses=addresses)


def validate_redirect_chain(
    urls: Iterable[str],
    *,
    allowed_hosts: set[str] | frozenset[str],
    resolver: HostResolver = system_resolver,
) -> list[ValidatedNetworkTarget]:
    return [
        validate_url_target(url, allowed_hosts=allowed_hosts, resolver=resolver) for url in urls
    ]


__all__ = [
    "HostResolver",
    "UnsafeNetworkTarget",
    "ValidatedNetworkTarget",
    "system_resolver",
    "validate_redirect_chain",
    "validate_url_target",
]
