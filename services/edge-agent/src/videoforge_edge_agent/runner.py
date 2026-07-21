"""Agent 主循环：注册 → 心跳 → 领取 → 执行 → 提交。

执行经 VF-006 注册表路由到本地 Provider（P0 全为 Fake）；提交摘要为
输出 JSON 的规范化 sha256，控制面按 task_id + output_digest 幂等。
"""

import asyncio
import hashlib
import json
import logging
import platform
import socket
from typing import Any

from videoforge_edge_agent.client import ControlPlaneClient
from videoforge_edge_agent.logsafe import scrub_text, secrets_from_env
from videoforge_edge_agent.toolchain import probe_toolchain
from videoforge_provider_sdk import NoEligibleProviderError, ProviderRegistry, route

logger = logging.getLogger("videoforge.edge_agent")


def output_digest(output: dict[str, Any]) -> str:
    canonical = json.dumps(output, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AgentRunner:
    def __init__(
        self,
        client: ControlPlaneClient,
        registry: ProviderRegistry,
        *,
        worker_name: str = "edge-agent",
        lease_ttl_s: int = 60,
        poll_interval_s: float = 2.0,
        heartbeat_interval_s: float = 30.0,
    ) -> None:
        self._client = client
        self._registry = registry
        self._worker_name = worker_name
        self._lease_ttl_s = lease_ttl_s
        self._poll_interval_s = poll_interval_s
        self._heartbeat_interval_s = heartbeat_interval_s
        self._secrets = secrets_from_env()
        self.worker_id: str | None = None

    @property
    def capabilities(self) -> list[str]:
        caps: set[str] = set()
        for entry in self._registry.all():
            caps.update(entry.provider.descriptor.capabilities)
        return sorted(caps)

    async def register(self) -> str:
        self.worker_id = await self._client.register(
            {
                "worker_id": self.worker_id,
                "name": self._worker_name,
                "hostname": socket.gethostname(),
                "os": platform.system().lower(),
                "arch": platform.machine(),
                "capabilities": self.capabilities,
                "execution_location": "local",
                "toolchain": probe_toolchain(),
            }
        )
        logger.info("registered worker_id=%s capabilities=%s", self.worker_id, self.capabilities)
        return self.worker_id

    async def run_once(self) -> bool:
        """领取并处理一个任务；无任务返回 False。"""
        assert self.worker_id is not None, "先 register()"
        envelope = await self._client.claim(
            worker_id=self.worker_id,
            capabilities=self.capabilities,
            lease_ttl_s=self._lease_ttl_s,
        )
        if envelope is None:
            return False
        assert envelope.lease_id is not None
        logger.info(
            "claimed task=%s capability=%s attempt=%d",
            envelope.task_id,
            envelope.capability,
            envelope.attempt,
        )
        try:
            decision = route(self._registry, envelope.capability)
            provider = self._registry.get(decision.selected).provider
            result = await provider.invoke(envelope.capability, envelope.params)
            self._registry.record_result(decision.selected, success=True)
        except NoEligibleProviderError as exc:
            # 上报服务端的失败文本同样过洗涤：异常消息可能夹带 Secret
            await self._client.fail(
                envelope.task_id,
                lease_id=envelope.lease_id,
                reason=scrub_text(str(exc), self._secrets),
            )
            logger.warning("task=%s 无可用 provider，已释放", envelope.task_id)
            return True
        except Exception as exc:
            await self._client.fail(
                envelope.task_id,
                lease_id=envelope.lease_id,
                reason=scrub_text(repr(exc), self._secrets),
            )
            logger.warning("task=%s 执行失败已释放: %r", envelope.task_id, exc)
            return True

        stored = await self._client.complete(
            envelope.task_id,
            lease_id=envelope.lease_id,
            output_digest=output_digest(result),
            output=result,
        )
        logger.info("task=%s 完成 stored=%s", envelope.task_id, stored)
        return True

    async def _heartbeat_loop(self) -> None:
        assert self.worker_id is not None
        while True:
            await asyncio.sleep(self._heartbeat_interval_s)
            try:
                await self._client.heartbeat(self.worker_id)
            except Exception as exc:  # 心跳失败不终止 agent，下轮重试
                logger.warning("heartbeat 失败: %r", exc)

    async def run_forever(self) -> None:
        await self.register()
        heartbeat = asyncio.create_task(self._heartbeat_loop())
        try:
            while True:
                worked = await self.run_once()
                if not worked:
                    await asyncio.sleep(self._poll_interval_s)
        finally:
            heartbeat.cancel()
