"""
테스트 공통 설정.

픽스처는 두 갈래다:
  · 합성 픽스처 — 실제 구조(중첩표·혼재 인코딩)를 재현. 커밋된다.
  · 실측 픽스처 — `data/raw/`의 실제 응답. gitignore 대상이라 없으면 건너뛴다.

실매출 수치가 저장소에 들어가지 않게 하면서도
"추측이 아닌 실제 응답"으로 검증한다는 CLAUDE.md 원칙을 지키기 위한 구조다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"


def _find_raw(report_type: str) -> Path | None:
    matches = sorted(RAW_DIR.rglob(f"{report_type}_*.html")) if RAW_DIR.exists() else []
    return matches[-1] if matches else None


@pytest.fixture
def raw_orders_html() -> str:
    path = _find_raw("orders")
    if path is None:
        pytest.skip("실측 픽스처 없음 — `python -m collector.main --days 7` 후 실행")
    from collector.formats import decode_korean
    return decode_korean(path.read_bytes())


@pytest.fixture
def raw_menu_html() -> str:
    path = _find_raw("menu")
    if path is None:
        pytest.skip("실측 픽스처 없음 — `python -m collector.main --days 7` 후 실행")
    from collector.formats import decode_korean
    return decode_korean(path.read_bytes())
