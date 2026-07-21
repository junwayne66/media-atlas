"""把 Pydantic 合同导出为 schemas/ 下的 JSON Schema 规范文件。

约定：Pydantic 是编写格式；提交进仓库的 schemas/*.schema.json 是评审与消费的
真值工件（docs/implementation/52-repo-structure.md）。CI 会重新导出并 diff，
防止两者漂移。用法：`uv run python -m videoforge_contracts.export [输出目录]`。
"""

import json
import sys
from pathlib import Path
from typing import Any

from videoforge_contracts import CONTRACTS

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_BASE = "https://videoforge.dev/schemas"


def generate_schema(name: str) -> dict[str, Any]:
    model = CONTRACTS[name]
    schema = model.model_json_schema(mode="validation")
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_BASE}/{name}.schema.json",
        **schema,
    }


def generate_all() -> dict[str, dict[str, Any]]:
    return {name: generate_schema(name) for name in CONTRACTS}


def render(schema: dict[str, Any]) -> str:
    # sort_keys + 固定缩进保证输出确定性，diff 才有意义
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in generate_all().items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(render(schema), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path(__file__).parents[4] / "schemas"
    for path in write_all(out_dir):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
