"""Provider 运行时协议与内置 Fake 实现。

业务模块只依赖本协议与结构化合同，不依赖任何第三方项目内部结构
（docs/README.md §4 规则 2）。各 Provider 类型的强类型调用接口随
对应模块任务（VF-2xx 起）逐个细化；注册/路由/健康层先行。
"""

from typing import Any, Protocol, runtime_checkable

from videoforge_contracts import HealthState, ProviderDescriptor


class ProviderInvokeError(Exception):
    """Provider 调用失败基类；错误映射由各 Connector 的 error_mapping 负责。"""


@runtime_checkable
class Provider(Protocol):
    descriptor: ProviderDescriptor

    async def health_check(self) -> HealthState: ...

    async def invoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class FakeProvider:
    """可编排失败与时延的内置 Fake，用于测试与 Fake→真实 的渐进替换。"""

    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self.descriptor = descriptor
        self._fail_remaining = 0
        self._health = HealthState.HEALTHY
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def fail_times(self, n: int) -> None:
        self._fail_remaining = n

    def set_health(self, health: HealthState) -> None:
        self._health = health

    async def health_check(self) -> HealthState:
        return self._health

    async def invoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        if capability not in self.descriptor.capabilities:
            raise ProviderInvokeError(f"{self.descriptor.name} 不支持能力 {capability}")
        self.calls.append((capability, payload))
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise ProviderInvokeError(f"{self.descriptor.name} 模拟失败")
        return {"provider": self.descriptor.name, "capability": capability, "echo": payload}
