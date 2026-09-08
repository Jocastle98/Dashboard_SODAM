"""
메뉴 표시명 별칭 (FN-251 / FR-DASH-14).

POS 원본 메뉴명이 화면에 그대로 내보내기 어려운 경우가 있다.
예: `초등학생(70g)` — 대상만 적혀 있어 무슨 상품인지 읽히지 않는다.

**DB와 POS 원본은 고치지 않는다.** 고쳐도 다음 수집에 POS 값으로 되돌아온다.
표시 단계에서만 갈아 끼운다.

메뉴명이 아니라 **메뉴코드**로 잡는다 — POS에서 이름 표기가 또 바뀌어도 별칭이 살아남는다.
API·단일 HTML·CSV 내보내기가 모두 이 모듈을 거치므로 이름이 한 곳에서만 정해진다.
"""

from __future__ import annotations

# 메뉴코드 → 화면에 보여줄 이름
ALIASES: dict[str, str] = {
    # `초등학생(70g)` — 카테고리는 월남쌈샤브샤브. 대상만 적혀 메뉴로 읽히지 않는다.
    "000067": "초등학생 월남쌈샤브 (70g)",
}


def display_name(menu_code: str | None, menu_name: str | None) -> str | None:
    """별칭이 있으면 그것을, 없으면 POS 원본 이름을 그대로 돌려준다."""
    if menu_code is None:
        return menu_name
    return ALIASES.get(str(menu_code), menu_name)
