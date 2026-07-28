import pytest

from videoforge_provider_sdk import (
    UnsafeNetworkTarget,
    validate_redirect_chain,
    validate_url_target,
)

DOUYIN_HOSTS = {"www.douyin.com", "v.douyin.com"}


def _public(_host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "http://www.douyin.com/video/7412345678901234567",
        "https://user@www.douyin.com/video/7412345678901234567",
        "https://www.douyin.com:444/video/7412345678901234567",
        "https://douyin.com.evil.test/video/7412345678901234567",
        "https://evil.test/douyin.com/video/7412345678901234567",
        "https://www.douyin.com@127.0.0.1/video/7412345678901234567",
        "file:///etc/passwd",
        "data:text/plain,hello",
        "https://www.douyin.com\\@127.0.0.1/video/7412345678901234567",
        "https://www%2edouyin.com/video/7412345678901234567",
    ],
)
def test_url_policy_rejects_confused_or_non_https_targets(url: str) -> None:
    with pytest.raises(UnsafeNetworkTarget):
        validate_url_target(url, allowed_hosts=DOUYIN_HOSTS, resolver=_public)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "224.0.0.1",
    ],
)
def test_url_policy_rejects_any_non_global_dns_answer(address: str) -> None:
    with pytest.raises(UnsafeNetworkTarget, match="公网"):
        validate_url_target(
            "https://www.douyin.com/video/7412345678901234567",
            allowed_hosts=DOUYIN_HOSTS,
            resolver=lambda _host: [address],
        )


def test_url_policy_accepts_allowlisted_https_with_public_dns() -> None:
    target = validate_url_target(
        "https://www.douyin.com/video/7412345678901234567",
        allowed_hosts=DOUYIN_HOSTS,
        resolver=lambda _host: ["1.1.1.1", "2606:4700:4700::1111"],
    )
    assert target.host == "www.douyin.com"
    assert target.addresses == ("1.1.1.1", "2606:4700:4700::1111")


def test_every_redirect_is_revalidated() -> None:
    with pytest.raises(UnsafeNetworkTarget):
        validate_redirect_chain(
            [
                "https://v.douyin.com/fixture/",
                "https://www.douyin.com/video/7412345678901234567",
                "https://127.0.0.1/internal",
            ],
            allowed_hosts=DOUYIN_HOSTS | {"127.0.0.1"},
            resolver=lambda host: ["127.0.0.1"] if host == "127.0.0.1" else ["1.1.1.1"],
        )
