"""向后兼容：历史版本的持久化样例必须始终可被当前模型解析。

规则（docs/architecture/31 §8）：Reader 至少兼容当前与前一版本。
每次 schema 升版时，把上一版的样例留在 fixtures/v<N>/ 不删除。
"""

import json
from pathlib import Path

import pytest

from videoforge_contracts import CONTRACTS

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES_DIR.glob("v*/*.json"))


def test_fixture_snapshot_exists() -> None:
    assert FIXTURE_FILES, "缺少兼容性 fixture；运行 tests/seed_fixtures.py 生成 v1 快照"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_historical_fixture_still_parses(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    model_cls = CONTRACTS[path.stem]
    parsed = model_cls.model_validate(payload)
    assert parsed.schema_version == payload["schema_version"]


def test_every_contract_has_current_version_fixture() -> None:
    current_dir = FIXTURES_DIR / "v1"
    missing = [name for name in CONTRACTS if not (current_dir / f"{name}.json").is_file()]
    assert not missing, f"缺少 v1 fixture: {missing}"
