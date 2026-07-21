"""agent 启动时容忍控制面暂不可达（出站重试）。"""

import httpx
import pytest

from videoforge_contracts import ProviderDescriptor
from videoforge_edge_agent.runner import AgentRunner
from videoforge_provider_sdk import FakeProvider, ProviderRegistry


class FlakyClient:
    """前 fail_times 次 register 抛 ConnectError，之后成功。"""

    def __init__(self, fail_times: int) -> None:
        self._remaining = fail_times
        self.register_calls = 0

    async def register(self, payload: dict) -> str:
        self.register_calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise httpx.ConnectError("control plane down")
        return "w-1"


def _registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(
        FakeProvider(
            ProviderDescriptor(
                name="source.fake",
                provider_type="SourceConnector",
                version="0.1.0",
                capabilities=["source.discover"],
                execution_location="local",
            )
        )
    )
    return reg


async def test_register_retries_until_control_plane_up() -> None:
    client = FlakyClient(fail_times=3)
    runner = AgentRunner(client, _registry())
    await runner._register_with_retry(attempts=10, backoff_s=0.0)
    assert runner.worker_id == "w-1"
    assert client.register_calls == 4  # 3 次失败 + 1 次成功


async def test_register_gives_up_after_max_attempts() -> None:
    client = FlakyClient(fail_times=100)
    runner = AgentRunner(client, _registry())
    with pytest.raises(httpx.ConnectError):
        await runner._register_with_retry(attempts=3, backoff_s=0.0)
    assert client.register_calls == 3
