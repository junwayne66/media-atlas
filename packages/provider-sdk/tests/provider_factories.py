from videoforge_contracts import CostModel, ProviderDescriptor
from videoforge_provider_sdk import FakeProvider


def make_descriptor(**overrides) -> ProviderDescriptor:
    values = {
        "name": "asr.fake",
        "provider_type": "ASRProvider",
        "version": "0.1.0",
        "capabilities": ["asr.transcribe"],
        "execution_location": "local",
    }
    values.update(overrides)
    return ProviderDescriptor(**values)


def make_provider(**overrides) -> FakeProvider:
    return FakeProvider(make_descriptor(**overrides))


def cost(per_unit: float) -> CostModel:
    return CostModel(unit="second", estimated_cost_per_unit=per_unit)
