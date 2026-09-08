"""
집계 테스트 — 시간대 유도와 휴무 판정.

시간대는 timeAnal 리포트를 수집하지 않고 주문의 판매시간에서 만든다.
실측에서 9개 시간대 전부 일치했지만, 그 규칙이 유지되는지 여기서 고정한다.
"""

from __future__ import annotations

from collector.aggregate import (
    aggregate_daily,
    aggregate_hourly,
    check_menu_consistency,
    check_payment_sums,
)
from collector.parse.orders import parse_orders
from tests import fixtures


def sample_orders():
    return parse_orders(fixtures.orders_html()).orders


# ── 시간대 유도 (docs/05 검증 3) ───────────────────────────

def test_hourly_is_derived_from_sold_at():
    hourly = aggregate_hourly(sample_orders())
    by_hour = {h.hour: h for h in hourly}
    assert set(by_hour) == {11, 13}                 # 11:02, 11:40, 13:23
    assert by_hour[11].order_count == 2
    assert by_hour[11].sales_amount == 30_000       # 10,000 + 20,000
    assert by_hour[13].order_count == 1


def test_hourly_totals_match_daily_total():
    orders = sample_orders()
    assert (sum(h.sales_amount for h in aggregate_hourly(orders))
            == sum(o.total_amt for o in orders))


def test_hourly_uses_sold_at_not_paid_at():
    """13:23 판매 / 14:21 결제 건이 13시로 잡혀야 한다."""
    hours = {h.hour for h in aggregate_hourly(sample_orders())}
    assert 13 in hours and 14 not in hours


# ── 일별 집계 ──────────────────────────────────────────────

def test_daily_totals():
    daily = aggregate_daily(sample_orders())
    assert len(daily) == 1
    day = daily[0]
    assert day.biz_date == "2026-08-15"
    assert day.sales_amount == 60_000
    assert day.order_count == 3
    assert day.cash_amt == 10_000
    assert day.card_amt == 50_000
    assert day.is_closed is False


def test_cancel_amount_comes_from_cancel_report():
    from collector.parse.cancels import parse_cancels
    daily = aggregate_daily(sample_orders(), parse_cancels(fixtures.cancels_html()))
    assert daily[0].cancel_amt == 30_000


# ── 휴무 판정 (DQ-02) ──────────────────────────────────────

def test_covered_day_without_orders_is_closed():
    """수집에 성공했는데 주문이 0건이면 휴무로 본다."""
    daily = aggregate_daily([], covered_dates=["2026-08-14"])
    assert len(daily) == 1
    assert daily[0].is_closed is True
    assert daily[0].sales_amount == 0


def test_uncovered_day_produces_no_row():
    """수집하지 않은 날은 행 자체가 없어야 한다 — 0원 매출로 오인하면 안 된다 (FR-DASH-12)."""
    daily = aggregate_daily(sample_orders())
    assert [d.biz_date for d in daily] == ["2026-08-15"]


# ── 품질 규칙 ──────────────────────────────────────────────

def test_dq03_passes_when_totals_match():
    daily = aggregate_daily(sample_orders())
    assert check_menu_consistency(daily, {"2026-08-15": 60_000}) == []


def test_dq03_flags_gap_over_one_percent():
    daily = aggregate_daily(sample_orders())
    issues = check_menu_consistency(daily, {"2026-08-15": 50_000})
    assert len(issues) == 1
    assert issues[0].rule == "DQ-03"


def test_dq03_ignores_closed_days():
    daily = aggregate_daily([], covered_dates=["2026-08-14"])
    assert check_menu_consistency(daily, {"2026-08-14": 999}) == []


def test_payment_sum_check_passes_on_real_structure():
    assert check_payment_sums(sample_orders()) == []
