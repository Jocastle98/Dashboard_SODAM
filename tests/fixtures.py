"""
합성 픽스처 — 실제 POS 응답의 구조적 함정을 그대로 재현한다.

재현하는 것:
  · 중첩 <table> — 모든 행을 합치면 데이터가 2배가 된다
  · 주문 리포트의 헤더가 데이터 표 밖에 있다
  · 데이터 표가 합계 행(No.=0)부터 시작한다
  · euc-kr 문서에 UTF-8 컬럼명이 섞여 있다
  · 금액에 콤마가 들어 있다

금액은 실제 매출이 아닌 가짜 숫자다 — 커밋해도 안전하다.
"""

from __future__ import annotations

ORDER_HEADER_CELLS = [
    "No.", "매장명", "주문번호", "판매시간", "결제시간", "총매출액", "할인액", "순매출액",
    "현금결제", "카드결제", "상품권", "포인트", "외상결제", "선수금", "부가세",
    "카드사", "매입사", "승인번호", "테이블명",
]


def _row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def _order_row(no: str, order_no: str, sold: str, paid: str, total: str,
               cash: str, card: str, vat: str, issuer: str, table: str) -> list[str]:
    return [no, "마곡점", order_no, sold, paid, total, "0", total,
            cash, card, "0", "0", "0", "0", vat, issuer, issuer, "12345678", table]


ORDER_ROWS = [
    _order_row("1", "202608150001", "2026-08-15 11:02", "2026-08-15 12:21",
               "10,000", "10,000", "0", "909", "", "20"),
    _order_row("2", "202608150002", "2026-08-15 11:40", "2026-08-15 12:22",
               "20,000", "0", "20,000", "1,818", "신한카드", "18"),
    _order_row("3", "202608150003", "2026-08-15 13:23", "2026-08-15 14:21",
               "30,000", "0", "30,000", "2,727", "우리카드", "7"),
]
TOTAL_ROW = ["0", "", "", "", "합계", "60,000", "0", "60,000",
             "10,000", "50,000", "0", "0", "0", "0", "5,454", "", "", "", ""]


def orders_html() -> str:
    """
    실제 구조 재현: 제목표 / 헤더표(중첩) / 데이터표.
    데이터표에는 헤더가 없고 합계 행부터 시작한다.
    """
    header_table = "<table>" + _row(ORDER_HEADER_CELLS) + "</table>"
    data_table = "<table>" + _row(TOTAL_ROW) + "".join(_row(r) for r in ORDER_ROWS) + "</table>"
    return f"""<html><body>
<table><tr><td>매장별매출세부내역 (소담촌 마곡점점)</td></tr>
       <tr><td>기간(20260815~20260815)</td></tr></table>
<table>{header_table}{data_table}</table>
</body></html>"""


def orders_bytes_mixed_encoding() -> bytes:
    """
    charset=euc-kr 선언이지만 '총매출액'/'순매출액'만 UTF-8로 나오는 실제 현상 재현.
    단일 인코딩으로는 디코딩 자체가 실패해야 한다.
    """
    html = orders_html()
    head, tail = html.split("총매출액", 1)
    tail_head, tail_rest = tail.split("순매출액", 1)
    return (head.encode("euc-kr") + "총매출액".encode("utf-8")
            + tail_head.encode("euc-kr") + "순매출액".encode("utf-8")
            + tail_rest.encode("euc-kr"))


MENU_HEADER_CELLS = ["순서", "분류명", "메뉴명", "메뉴코드", "총매출액", "일평균매출액", "판매수량"]
MENU_ROWS = [
    ["1", "월남쌈샤브샤브", "월남쌈샤브(120g)", "000012", "40,000", "40,000", "4"],
    ["2", "점심특선", "월남쌈샤브(70g)", "000006", "20,000", "20,000", "2"],
]


def menu_html() -> str:
    """메뉴 리포트는 데이터 표 안에 헤더가 있다."""
    rows = _row(MENU_HEADER_CELLS) + "".join(_row(r) for r in MENU_ROWS)
    return f"""<html><body>
<table><tr><td>메뉴별매출현황 (소담촌 마곡점점)</td></tr></table>
<table>{rows}</table>
</body></html>"""


CANCEL_HEADER_CELLS = ["No.", "매장", "구분", "주문번호", "판매시간", "취소시간",
                       "품목", "수량", "금액", "취소사유"]
CANCEL_ROWS = [
    ["1", "마곡점", "전체취소", "20260815-0043", "18:05", "18:05", "반반", "1", "0", ""],
    ["2", "마곡점", "전체취소", "20260815-0043", "18:05", "18:05", "반반(육수)", "1", "0", ""],
    ["3", "마곡점", "부분취소", "20260815-0044", "19:10", "19:30", "월남쌈샤브(120g)", "2", "30,000", "고객요청"],
]


def cancels_html() -> str:
    rows = _row(CANCEL_HEADER_CELLS) + "".join(_row(r) for r in CANCEL_ROWS)
    return f"<html><body><table>{rows}</table></body></html>"
