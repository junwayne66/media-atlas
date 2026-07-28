"""端到端：真实 API 路由 + 真实 Postgres + agent 主循环（ASGITransport 无端口）。"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from videoforge_contracts import ExecutionPolicy, TaskEnvelope
from videoforge_edge_agent.client import ControlPlaneClient
from videoforge_edge_agent.main import build_registry
from videoforge_edge_agent.runner import AgentRunner, output_digest
from videoforge_provider_sdk import FakeProvider, ProviderRegistry, scan_descriptors

REPO_ROOT = Path(__file__).parents[3]


class _SlowProvider(FakeProvider):
    async def invoke(self, capability, payload):
        await asyncio.sleep(10)
        return await super().invoke(capability, payload)


class _LeaseLosingClient:
    def __init__(self, envelope: TaskEnvelope) -> None:
        self.envelope = envelope
        self.renewed = 0
        self.completed = 0
        self.failed = 0

    async def register(self, payload):
        return "worker-unit"

    async def claim(self, **kwargs):
        out, self.envelope = self.envelope, None
        return out

    async def renew(self, *args, **kwargs):
        self.renewed += 1
        request = httpx.Request("POST", "http://control/renew")
        response = httpx.Response(409, request=request)
        raise httpx.HTTPStatusError("lease lost", request=request, response=response)

    async def complete(self, *args, **kwargs):
        self.completed += 1
        return True

    async def fail(self, *args, **kwargs):
        self.failed += 1


async def test_task_renewal_loss_cancels_provider_and_forbids_submit() -> None:
    descriptors = {d.name: d for d in scan_descriptors(REPO_ROOT / "connectors")}
    registry = ProviderRegistry()
    registry.register(_SlowProvider(descriptors["source.fake"]))
    envelope = TaskEnvelope(
        task_id="task-unit",
        idempotency_key="task-unit",
        capability="source.discover",
        execution_policy=ExecutionPolicy.LOCAL_ONLY,
        attempt=1,
        lease_id="lease-unit",
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=1),
        params={"platform": "douyin"},
        created_at=datetime.now(UTC),
    )
    client = _LeaseLosingClient(envelope)
    runner = AgentRunner(client, registry, lease_ttl_s=1)
    runner.worker_id = "worker-unit"

    assert await runner.run_once() is True
    assert client.renewed == 1
    assert client.completed == 0
    assert client.failed == 0


async def _enqueue(control_plane: ControlPlaneClient, capability: str, key: str) -> str:
    resp = await control_plane._http.post(
        "/v1/worker-tasks",
        json={"capability": capability, "params": {"topic": "ai"}, "idempotency_key": key},
    )
    resp.raise_for_status()
    return resp.json()["task_id"]


async def _status(control_plane: ControlPlaneClient, task_id: str) -> dict:
    resp = await control_plane._http.get(f"/v1/worker-tasks/{task_id}")
    resp.raise_for_status()
    return resp.json()


async def test_fake_source_to_fake_render_flow(control_plane: ControlPlaneClient) -> None:
    """P0 Exit 雏形：Fake Source 与 Fake Render 任务由本地 worker 领取完成。"""
    runner = AgentRunner(
        control_plane, build_registry(REPO_ROOT / "connectors"), worker_name="test-agent"
    )
    await runner.register()
    assert "source.discover" in runner.capabilities
    assert "render.compose" in runner.capabilities

    t_source = await _enqueue(control_plane, "source.discover", "e2e-source")
    t_render = await _enqueue(control_plane, "render.compose", "e2e-render")

    assert await runner.run_once() is True
    assert await runner.run_once() is True
    assert await runner.run_once() is False  # 队列空

    for task_id, capability in ((t_source, "source.discover"), (t_render, "render.compose")):
        status = await _status(control_plane, task_id)
        assert status["status"] == "COMPLETED"
        if capability == "source.discover":
            # Douyin 已升级为零网络 Fixture Provider；其他连接器仍走 Fake。
            assert status["output"]["status"] == "SUCCEEDED"
            assert status["output"]["result"]["platform"] == "douyin"
        else:
            assert status["output"]["capability"] == capability
        assert status["output_digest"] == output_digest(status["output"])

    await control_plane.heartbeat(runner.worker_id)  # 心跳链路可用


async def test_provider_failure_releases_then_retry_succeeds(
    control_plane: ControlPlaneClient,
) -> None:
    registry = ProviderRegistry()
    descriptors = {d.name: d for d in scan_descriptors(REPO_ROOT / "connectors")}
    provider = FakeProvider(descriptors["source.fake"])  # 按名选，不依赖扫描顺序
    assert provider.descriptor.name == "source.fake"
    provider.fail_times(1)
    registry.register(provider)

    runner = AgentRunner(control_plane, registry, worker_name="flaky-agent")
    await runner.register()
    task_id = await _enqueue(control_plane, "source.discover", "e2e-flaky")

    assert await runner.run_once() is True  # 第一次执行失败 → fail 释放
    status = await _status(control_plane, task_id)
    assert status["status"] == "PENDING"
    assert status["output"]["last_error"]

    assert await runner.run_once() is True  # 重领重试成功
    status = await _status(control_plane, task_id)
    assert status["status"] == "COMPLETED"
    assert status["attempt"] == 2


async def test_renew_and_stale_complete_conflict(control_plane: ControlPlaneClient) -> None:
    await _enqueue(control_plane, "source.discover", "e2e-lease")
    envelope = await control_plane.claim(
        worker_id=(
            await control_plane.register(
                {
                    "name": "w-lease",
                    "hostname": "h",
                    "os": "darwin",
                    "arch": "arm64",
                    "capabilities": ["source.discover"],
                    "execution_location": "local",
                }
            )
        ),
        capabilities=["source.discover"],
        lease_ttl_s=60,
    )
    assert envelope is not None
    renewed = await control_plane.renew(
        envelope.task_id, lease_id=envelope.lease_id, lease_ttl_s=120
    )
    assert renewed > envelope.lease_expires_at

    with pytest.raises(httpx.HTTPStatusError) as exc:
        await control_plane.complete(
            envelope.task_id, lease_id="stale-lease", output_digest="d" * 64, output={}
        )
    assert exc.value.response.status_code == 409
