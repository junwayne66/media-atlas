"""控制面客户端：Worker 只发起出站连接，不暴露入站端口（30 §5）。"""

from datetime import datetime
from typing import Any

import httpx

from videoforge_contracts import TaskEnvelope


class ControlPlaneClient:
    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        # 测试可注入 ASGITransport 的 client，全链路不开真实端口
        self._http = client or httpx.AsyncClient(base_url=base_url, timeout=30)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def register(self, payload: dict[str, Any]) -> str:
        resp = await self._http.post("/v1/workers/register", json=payload)
        resp.raise_for_status()
        return resp.json()["worker_id"]

    async def heartbeat(self, worker_id: str) -> None:
        resp = await self._http.post(f"/v1/workers/{worker_id}/heartbeat")
        resp.raise_for_status()

    async def claim(
        self, *, worker_id: str, capabilities: list[str], lease_ttl_s: int
    ) -> TaskEnvelope | None:
        resp = await self._http.post(
            "/v1/worker-tasks/claim",
            json={
                "worker_id": worker_id,
                "capabilities": capabilities,
                "lease_ttl_s": lease_ttl_s,
            },
        )
        resp.raise_for_status()
        if resp.status_code == 204:
            return None
        return TaskEnvelope.model_validate_json(resp.content)

    async def renew(self, task_id: str, *, lease_id: str, lease_ttl_s: int) -> datetime:
        resp = await self._http.post(
            f"/v1/worker-tasks/{task_id}/renew",
            json={"lease_id": lease_id, "lease_ttl_s": lease_ttl_s},
        )
        resp.raise_for_status()
        return datetime.fromisoformat(resp.json()["lease_expires_at"])

    async def complete(
        self, task_id: str, *, lease_id: str, output_digest: str, output: dict[str, Any]
    ) -> bool:
        resp = await self._http.post(
            f"/v1/worker-tasks/{task_id}/complete",
            json={"lease_id": lease_id, "output_digest": output_digest, "output": output},
        )
        resp.raise_for_status()
        return resp.json()["stored"]

    async def fail(self, task_id: str, *, lease_id: str, reason: str) -> None:
        resp = await self._http.post(
            f"/v1/worker-tasks/{task_id}/fail",
            json={"lease_id": lease_id, "reason": reason},
        )
        resp.raise_for_status()
