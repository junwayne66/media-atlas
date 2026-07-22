import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_tiktok_fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
