"""
주문 상세 리포트 파서 — `agentAnal_com_excel01.asp`.

주문(영수증) 단위 19컬럼. 일별 매출·결제수단·시간대의 원천이 된다.
컬럼 구성은 docs/03_POS_분석결과.md 2.1 참고.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tables import (
    ParseError,
    biz_date_from_order_no,
    find_total_row,
    is_data_row,
    normalize_order_no,
    optional,
    select_report,
    to_datetime,
    to_int,
    verify_header,
)

COLUMN_COUNT = 19

# POS 원문 컬럼 순서 (docs/03 2.1). 인덱스가 곧 계약이다.
NO, STORE, ORDER_NO, SOLD_AT, PAID_AT = 0, 1, 2, 3, 4
TOTAL, DISCOUNT, NET = 5, 6, 7
CASH, CARD, GIFT, POINT, CREDIT, PREPAID = 8, 9, 10, 11, 12, 13
VAT, CARD_ISSUER, CARD_ACQUIRER, APPROVAL, TABLE = 14, 15, 16, 17, 18

EXPECTED_HEADER = ("No.", "매장명", "주문번호", "판매시간", "결제시간", "총매출액")


@dataclass(frozen=True)
class Order:
    order_no: str
    biz_date: str
    sold_at: str
    paid_at: str | None
    total_amt: int
    discount_amt: int
    net_amt: int
    vat_amt: int
    cash_amt: int
    card_amt: int
    gift_amt: int
    point_amt: int
    credit_amt: int
    prepaid_amt: int
    card_issuer: str | None
    card_acquirer: str | None
    table_name: str | None

    @property
    def payment_sum(self) -> int:
        """결제수단 6종 합. 실측상 total_amt와 일치한다 (검증용)."""
        return (self.cash_amt + self.card_amt + self.gift_amt
                + self.point_amt + self.credit_amt + self.prepaid_amt)


@dataclass(frozen=True)
class OrderReport:
    orders: list[Order]
    total_amount: int | None  # 합계 행의 총매출액 — 파싱 검증용
    total_discount: int | None


def parse_orders(html: str) -> OrderReport:
    report = select_report(html, COLUMN_COUNT, EXPECTED_HEADER[0])
    verify_header(report.header, EXPECTED_HEADER)
    rows = report.rows

    orders = [_to_order(row) for row in rows if is_data_row(row)]

    total_row = find_total_row(rows)
    return OrderReport(
        orders=orders,
        total_amount=to_int(total_row[TOTAL]) if total_row else None,
        total_discount=to_int(total_row[DISCOUNT]) if total_row else None,
    )


def _to_order(row: list[str]) -> Order:
    order_no = normalize_order_no(row[ORDER_NO])
    sold_at = to_datetime(row[SOLD_AT])
    if not sold_at:
        raise ParseError(f"판매시간을 읽을 수 없습니다: {row[SOLD_AT]!r} (주문 {order_no})")

    return Order(
        order_no=order_no,
        biz_date=biz_date_from_order_no(order_no),
        sold_at=sold_at,
        paid_at=to_datetime(row[PAID_AT]),
        total_amt=to_int(row[TOTAL]),
        discount_amt=to_int(row[DISCOUNT]),
        net_amt=to_int(row[NET]),
        vat_amt=to_int(row[VAT]),
        cash_amt=to_int(row[CASH]),
        card_amt=to_int(row[CARD]),
        gift_amt=to_int(row[GIFT]),
        point_amt=to_int(row[POINT]),
        credit_amt=to_int(row[CREDIT]),
        prepaid_amt=to_int(row[PREPAID]),
        card_issuer=optional(row[CARD_ISSUER]),
        card_acquirer=optional(row[CARD_ACQUIRER]),
        table_name=optional(row[TABLE]),
    )
    # row[APPROVAL] (승인번호)은 의도적으로 읽지 않는다 — SRS 6.3
