"""
POS 응답 파서.

세 리포트(주문·메뉴·취소)를 표준 형태로 정규화한다.
표 선택과 값 정규화 규칙은 `tables.py` 한 곳에만 둔다 —
파서마다 따로 두면 한쪽만 고쳐져 조용히 어긋난다.
"""

from .cancels import Cancel, parse_cancels
from .menu import MenuSale, parse_menu
from .orders import Order, parse_orders

__all__ = [
    "Order", "parse_orders",
    "MenuSale", "parse_menu",
    "Cancel", "parse_cancels",
]
