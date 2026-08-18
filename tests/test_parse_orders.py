"""
주문 리포트 파서 테스트.

docs/05 6장의 검증 항목을 고정한다. 특히 중첩표 중복은
오류 없이 매출만 2배로 만들기 때문에 반드시 테스트로 막아야 한다.
"""

from __future__ import annotations

import pytest

from collector.formats import decode_korean
from collector.parse.orders import parse_orders
from collector.parse.tables import ParseError, select_report
from tests import fixtures


# ── 중첩표 중복 (docs/05 검증 1) ───────────────────────────

def test_nested_tables_do_not_double_rows():
    """모든 표의 행을 합치면 2배가 된다. 표 하나만 골라야 한다."""
    report = parse_orders(fixtures.orders_html())
    assert len(report.orders) == len(fixtures.ORDER_ROWS)


def test_selected_table_contains_every_order_once():
    report = select_report(fixtures.orders_html(), 19, "No.")
    order_numbers = [row[2] for row in report.rows if row[0].isdigit() and row[0] != "0"]
    assert order_numbers == [row[2] for row in fixtures.ORDER_ROWS]


def test_duplicate_rows_are_collapsed():
    """표 선택이 잘못돼 같은 행이 두 번 잡혀도 매출이 2배가 되면 안 된다."""
    doubled = fixtures.orders_html().replace("</table>\n</body>", "</table>\n</body>")
    rows = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in fixtures.ORDER_ROWS
    )
    injected = fixtures.orders_html().replace("</body>", f"<table>{rows}{rows}</table></body>")
    report = parse_orders(injected)
    assert len(report.orders) == len(fixtures.ORDER_ROWS)
    assert sum(o.total_amt for o in report.orders) == 60_000
    assert doubled == fixtures.orders_html()


# ── 합계 행 (docs/05 검증 2) ───────────────────────────────

def test_total_row_is_not_loaded_as_an_order():
    report = parse_orders(fixtures.orders_html())
    assert all(order.order_no != "0" for order in report.orders)
    assert report.total_amount == 60_000


def test_parsed_orders_sum_to_the_total_row():
    report = parse_orders(fixtures.orders_html())
    assert sum(order.total_amt for order in report.orders) == report.total_amount


# ── 결제수단 (docs/05 검증 5) ──────────────────────────────

def test_payment_methods_sum_to_total():
    for order in parse_orders(fixtures.orders_html()).orders:
        assert order.payment_sum == order.total_amt


# ── 값 정규화 ──────────────────────────────────────────────

def test_amounts_lose_their_commas():
    first = parse_orders(fixtures.orders_html()).orders[0]
    assert first.total_amt == 10_000
    assert first.vat_amt == 909


def test_biz_date_comes_from_order_no():
    first = parse_orders(fixtures.orders_html()).orders[0]
    assert first.order_no == "202608150001"
    assert first.biz_date == "2026-08-15"


def test_blank_cells_become_none():
    first = parse_orders(fixtures.orders_html()).orders[0]
    assert first.card_issuer is None      # 현금 결제라 카드사가 빈 칸
    assert first.table_name == "20"


def test_approval_number_is_not_exposed():
    """승인번호는 저장하지 않는다 (SRS 6.3)."""
    first = parse_orders(fixtures.orders_html()).orders[0]
    assert not hasattr(first, "approval_no")
    assert "12345678" not in str(first)


# ── 인코딩 혼재 (docs/05 검증 7) ───────────────────────────

def test_mixed_encoding_response_parses():
    content = fixtures.orders_bytes_mixed_encoding()
    for encoding in ("euc-kr", "utf-8"):
        with pytest.raises(UnicodeDecodeError):
            content.decode(encoding)
    report = parse_orders(decode_korean(content))
    assert len(report.orders) == len(fixtures.ORDER_ROWS)


# ── 구조 변경 감지 ─────────────────────────────────────────

def test_changed_column_order_raises():
    broken = fixtures.orders_html().replace("<td>주문번호</td>", "<td>주문번호변경</td>")
    with pytest.raises(ParseError, match="컬럼 구성"):
        parse_orders(broken)


def test_missing_table_raises():
    with pytest.raises(ParseError):
        parse_orders("<html><body><p>데이터 없음</p></body></html>")
