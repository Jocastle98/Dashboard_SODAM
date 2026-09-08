"""
집계 — 주문에서 일별·시간대별을 만든다.

POS를 다시 조회하지 않는다. `orders`만 있으면 언제든 재생성할 수 있고,
집계 규칙이 틀렸다고 밝혀져도 원본은 그대로다.

시간대는 `timeAnal` 리포트를 수집하지 않고 `sold_at`에서 유도한다.
유도값이 실측과 9개 시간대 전부 일치함을 확인했다 (docs/05 0장).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .parse.cancels import Cancel
from .parse.orders import Order
from .parse.tables import hour_of


@dataclass(frozen=True)
class DailySales:
    biz_date: str
    sales_amount: int
    order_count: int
    discount_amt: int
    cancel_amt: int
    vat_amt: int
    cash_amt: int
    card_amt: int
    etc_amt: int          # 상품권+포인트+외상+선수금
    is_closed: bool


@dataclass(frozen=True)
class HourlySales:
    biz_date: str
    hour: int
    sales_amount: int
    order_count: int


def aggregate_daily(
    orders: list[Order],
    cancels: list[Cancel] | None = None,
    covered_dates: list[str] | None = None,
) -> list[DailySales]:
    """
    주문을 일별로 집계한다.

    `covered_dates` — 수집을 시도해 성공한 날짜 목록.
    주문이 하나도 없는 날을 '휴무'로 기록하기 위해 필요하다 (DQ-02).
    넘기지 않으면 주문이 있는 날만 돌려준다.
    """
    cancel_by_date: dict[str, int] = defaultdict(int)
    for cancel in cancels or []:
        cancel_by_date[cancel.biz_date] += cancel.amount

    grouped: dict[str, list[Order]] = defaultdict(list)
    for order in orders:
        grouped[order.biz_date].append(order)

    dates = sorted(set(grouped) | set(covered_dates or []))
    return [_daily_of(date, grouped.get(date, []), cancel_by_date.get(date, 0)) for date in dates]


def _daily_of(biz_date: str, orders: list[Order], cancel_amt: int) -> DailySales:
    return DailySales(
        biz_date=biz_date,
        sales_amount=sum(o.total_amt for o in orders),
        order_count=len(orders),
        discount_amt=sum(o.discount_amt for o in orders),
        cancel_amt=cancel_amt,
        vat_amt=sum(o.vat_amt for o in orders),
        cash_amt=sum(o.cash_amt for o in orders),
        card_amt=sum(o.card_amt for o in orders),
        etc_amt=sum(o.gift_amt + o.point_amt + o.credit_amt + o.prepaid_amt for o in orders),
        # DQ-02: 수집에 성공했는데 주문이 0건이면 휴무로 본다.
        # POS가 휴무 여부를 알려주지 않으므로 이는 추론이다.
        is_closed=not orders,
    )


def aggregate_hourly(orders: list[Order]) -> list[HourlySales]:
    """`sold_at`의 시(hour)로 묶는다. 판매시간 기준이 실측과 일치했다."""
    buckets: dict[tuple[str, int], list[Order]] = defaultdict(list)
    for order in orders:
        hour = hour_of(order.sold_at)
        if hour is None:
            continue
        buckets[(order.biz_date, hour)].append(order)

    return [
        HourlySales(
            biz_date=biz_date,
            hour=hour,
            sales_amount=sum(o.total_amt for o in group),
            order_count=len(group),
        )
        for (biz_date, hour), group in sorted(buckets.items())
    ]


# ── 품질 검증 (DQ-03) ──────────────────────────────────────

@dataclass(frozen=True)
class QualityIssue:
    biz_date: str
    rule: str
    message: str


def check_menu_consistency(
    daily: list[DailySales],
    menu_total_by_date: dict[str, int],
    tolerance: float = 0.01,
) -> list[QualityIssue]:
    """
    DQ-03 — 일별 매출 합계와 메뉴별 매출 합계의 오차가 1%를 넘으면 경고.
    2026-08-15 실측에서는 오차 0.00%였다.
    """
    issues: list[QualityIssue] = []
    for day in daily:
        if day.is_closed or day.sales_amount == 0:
            continue
        menu_total = menu_total_by_date.get(day.biz_date)
        if menu_total is None:
            continue
        gap = abs(menu_total - day.sales_amount) / day.sales_amount
        if gap > tolerance:
            issues.append(QualityIssue(
                biz_date=day.biz_date,
                rule="DQ-03",
                message=(f"메뉴 합계 {menu_total:,} vs 일별 매출 {day.sales_amount:,} "
                         f"— 오차 {gap * 100:.2f}%"),
            ))
    return issues


def check_payment_sums(orders: list[Order]) -> list[QualityIssue]:
    """결제수단 6종 합이 총매출과 다르면 파싱이 어긋난 것이다."""
    return [
        QualityIssue(
            biz_date=order.biz_date,
            rule="PAYMENT_SUM",
            message=(f"주문 {order.order_no}: 결제수단 합 {order.payment_sum:,} "
                     f"≠ 총매출 {order.total_amt:,}"),
        )
        for order in orders if order.payment_sum != order.total_amt
    ]
