"""메뉴·취소 리포트 파서 테스트."""

from __future__ import annotations

import pytest

from collector.parse.cancels import parse_cancels
from collector.parse.menu import parse_menu
from collector.parse.tables import ParseError
from tests import fixtures

BIZ_DATE = "2026-08-15"


# ── 메뉴 ───────────────────────────────────────────────────

def test_menu_rows_are_parsed():
    sales = parse_menu(fixtures.menu_html(), BIZ_DATE)
    assert len(sales) == len(fixtures.MENU_ROWS)
    assert sales[0].menu_name == "월남쌈샤브(120g)"
    assert sales[0].category == "월남쌈샤브샤브"
    assert sales[0].sales_amount == 40_000
    assert sales[0].quantity == 4


def test_menu_code_keeps_leading_zeros():
    """'000012'를 정수로 바꾸면 앞의 0이 날아가 다른 메뉴가 된다."""
    sales = parse_menu(fixtures.menu_html(), BIZ_DATE)
    assert sales[0].menu_code == "000012"
    assert isinstance(sales[0].menu_code, str)


def test_menu_takes_biz_date_from_caller():
    """메뉴 리포트 본문에는 날짜가 없다 — 조회한 날짜를 호출부가 알려줘야 한다."""
    sales = parse_menu(fixtures.menu_html(), "2025-01-02")
    assert all(sale.biz_date == "2025-01-02" for sale in sales)


def test_duplicate_menu_codes_raise():
    """중첩표를 잘못 고르면 같은 코드가 두 번 나온다 — 적재에서 덮어써지기 전에 막는다."""
    broken = fixtures.menu_html().replace("000006", "000012")
    with pytest.raises(ParseError, match="중복"):
        parse_menu(broken, BIZ_DATE)


def test_menu_daily_average_is_not_stored():
    sale = parse_menu(fixtures.menu_html(), BIZ_DATE)[0]
    assert not hasattr(sale, "daily_avg")


# ── 취소 ───────────────────────────────────────────────────

def test_cancel_order_no_is_normalized():
    """취소 리포트는 '20260815-0043', 주문 리포트는 '202608150043' 형식으로 준다."""
    cancels = parse_cancels(fixtures.cancels_html())
    assert cancels[0].order_no == "202608150043"
    assert cancels[0].biz_date == "2026-08-15"


def test_multiple_items_in_one_order_get_sequence_numbers():
    cancels = parse_cancels(fixtures.cancels_html())
    same_order = [c for c in cancels if c.order_no == "202608150043"]
    assert [c.seq for c in same_order] == [1, 2]


def test_time_only_values_are_combined_with_biz_date():
    """취소 리포트는 '18:05'처럼 시각만 준다."""
    cancels = parse_cancels(fixtures.cancels_html())
    assert cancels[0].sold_at == "2026-08-15 18:05"


def test_partial_cancel_keeps_amount_and_reason():
    cancels = parse_cancels(fixtures.cancels_html())
    partial = next(c for c in cancels if c.cancel_type == "부분취소")
    assert partial.amount == 30_000
    assert partial.reason == "고객요청"
    assert partial.quantity == 2


def test_no_cancels_returns_empty_list():
    """취소가 없는 날은 데이터 표 자체가 나오지 않는다 — 예외가 아니라 빈 목록."""
    assert parse_cancels("<html><body><p>내역 없음</p></body></html>") == []
