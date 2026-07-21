"""schemas/ 目录（提交的真值工件）必须与当前模型的导出完全一致。"""

from pathlib import Path

import pytest

from videoforge_contracts import CONTRACTS
from videoforge_contracts.export import generate_schema, render

SCHEMAS_DIR = Path(__file__).parents[3] / "schemas"


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_committed_schema_matches_model(name: str) -> None:
    path = SCHEMAS_DIR / f"{name}.schema.json"
    assert path.is_file(), f"缺少 {path}；运行 `uv run python -m videoforge_contracts.export` 生成"
    assert path.read_text(encoding="utf-8") == render(generate_schema(name)), (
        f"{path.name} 与模型不一致；重新运行导出并提交"
    )


def test_no_orphan_schema_files() -> None:
    expected = {f"{name}.schema.json" for name in CONTRACTS}
    actual = {p.name for p in SCHEMAS_DIR.glob("*.schema.json")}
    assert actual == expected
