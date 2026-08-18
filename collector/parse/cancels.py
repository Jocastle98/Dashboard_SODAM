"""
주문 취소내역 파서 — `agentAnal_com_excel03.asp`.

10컬럼: No. / 매장 / 구분 / 주문번호 / 판매시간 / 취소시간 / 품목 / 수량 / 금액 / 취소사유

품목 단위로 나온다. 한 주문에 여러 행이 올 수 있다 (DQ-01 취소 건 분류의 근거).

⚠ 두 가지가 주문 리포트와 다르다:
  · 주문번호 형식 — `20260815-0043` (주문 리포트는 `202608150043`)
  · 시각만 준다  — `18:05` (날짜 없음)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .tables import (
    ParseError,
    biz_date_from_order_no,
    clean,
    is_data_row,
    normalize_order_no,
    optional,
    select_report,
    to_datetime_on,
    to_int,
    verify_header,
)

COLUMN_COUNT = 10

NO, STORE, CANCEL_TYPE, ORDER_NO, SOLD_AT, CANCELED_AT, ITEM, QUANTITY, AMOUNT, REASON = range(10)

EXPECTED_HEADER = ("No.", "매장", "구분", "주문번호", "판매시간", "취소시간", "품목")


@dataclass(frozen=True)
class Cancel:
    biz_date: str
    order_no: str
    seq: int            # 같은 주문 안의 품목 순번
    cancel_type: str | None
    sold_at: str | None
    canceled_at: str | None
    item_name: str | None
    quantity: int
    amount: int
    reason: str | None


def parse_cancels(html: str) -> list[Cancel]:
    """취소 건이 없는 날은 빈 목록을 돌려준다 (표 자체가 비어 있는 것은 정상)."""
    try:
        report = select_report(html, COLUMN_COUNT, EXPECTED_HEADER[0])
    except ParseError:
        return []  # 해당 기간에 취소가 없으면 데이터 표가 아예 나오지 않는다

    verify_header(report.header, EXPECTED_HEADER)
    rows = report.rows

    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    cancels: list[Cancel] = []
    for row in rows:
        if not is_data_row(row):
            continue
        order_no = normalize_order_no(row[ORDER_NO])
        biz_date = biz_date_from_order_no(order_no)
        counters[(biz_date, order_no)] += 1
        cancels.append(_to_cancel(row, biz_date, order_no, counters[(biz_date, order_no)]))
    return cancels


def _to_cancel(row: list[str], biz_date: str, order_no: str, seq: int) -> Cancel:
    return Cancel(
        biz_date=biz_date,
        order_no=order_no,
        seq=seq,
        cancel_type=optional(row[CANCEL_TYPE]),
        sold_at=to_datetime_on(biz_date, row[SOLD_AT]),
        canceled_at=to_datetime_on(biz_date, row[CANCELED_AT]),
        item_name=optional(row[ITEM]),
        quantity=to_int(row[QUANTITY]),
        amount=to_int(row[AMOUNT]),
        reason=optional(row[REASON]),
    )
