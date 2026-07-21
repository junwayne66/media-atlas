import pytest
from samples import SAMPLES

from videoforge_contracts import CONTRACTS, ProblemDetail


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_json_roundtrip_is_lossless(name: str) -> None:
    model_cls = CONTRACTS[name]
    original = SAMPLES[name]
    reparsed = model_cls.model_validate_json(original.model_dump_json())
    assert reparsed == original
    assert reparsed.model_dump() == original.model_dump()


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_samples_carry_schema_version(name: str) -> None:
    assert SAMPLES[name].schema_version == "1"


def test_problem_detail_preserves_extensions() -> None:
    original = ProblemDetail.model_validate({"title": "Boom", "status": 500, "trace_id": "t-123"})
    reparsed = ProblemDetail.model_validate_json(original.model_dump_json())
    assert reparsed.model_dump()["trace_id"] == "t-123"
