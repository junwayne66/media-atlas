"""生成当前 schema 版本的兼容性 fixture 快照（每个版本只生成一次并提交）。

用法：uv run python packages/contracts-py/tests/seed_fixtures.py
已存在的版本目录不会被覆盖——历史快照是不可变的兼容性证据。
"""

import json
import sys
from pathlib import Path

from samples import SAMPLES

from videoforge_contracts import CONTRACT_SCHEMA_VERSION


def main() -> int:
    out_dir = Path(__file__).parent / "fixtures" / f"v{CONTRACT_SCHEMA_VERSION}"
    if out_dir.exists():
        print(f"{out_dir} 已存在，历史快照不可覆盖；如需重建请手动删除后重跑")
        return 1
    out_dir.mkdir(parents=True)
    for name, sample in SAMPLES.items():
        path = out_dir / f"{name}.json"
        payload = json.loads(sample.model_dump_json())
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
