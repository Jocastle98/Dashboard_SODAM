"""
메뉴별 매출 리포트 파서 — `menuAnal_sub_1_excel.asp`.

7컬럼: 순서 / 분류명 / 메뉴명 / 메뉴코드 / 총매출액 / 일평균매출액 / 판매수량

⚠ 이 리포트는 조회 기간 전체를 **합산**해서 준다. 일별로 분해할 수 없으므로
  날짜별 데이터가 필요하면 하루씩 조회해야 한다 (docs/05 1장).
  따라서 파서는 `biz_date`를 인자로 받는다 — 응답에는 날짜가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tables import ParseError, clean, is_data_row, select_report, to_int, verify_header

COLUMN_COUNT = 7

SEQ, CATEGORY, MENU_NAME, MENU_CODE, SALES, DAILY_AVG, QUANTITY = range(7)

EXPECTED_HEADER = ("순서", "분류명", "메뉴명", "메뉴코드", "총매출액")


@dataclass(frozen=True)
class MenuSale:
    biz_date: str
    menu_code: str      # '000012' — 앞의 0을 살리려면 반드시 문자열
    menu_name: str
    category: str | None
    sales_amount: int
    quantity: int


def parse_menu(html: str, biz_date: str) -> list[MenuSale]:
    """`biz_date`는 조회한 날짜. 응답 본문에 날짜가 없어 호출부가 알려줘야 한다."""
    report = select_report(html, COLUMN_COUNT, EXPECTED_HEADER[0])
    verify_header(report.header, EXPECTED_HEADER)
    rows = report.rows

    sales = [_to_menu_sale(row, biz_date) for row in rows if is_data_row(row)]
    _verify_unique_codes(sales)
    return sales


def _to_menu_sale(row: list[str], biz_date: str) -> MenuSale:
    menu_code = clean(row[MENU_CODE])
    if not menu_code:
        raise ParseError(f"메뉴코드가 비어 있습니다: {row!r}")
    return MenuSale(
        biz_date=biz_date,
        menu_code=menu_code,
        menu_name=clean(row[MENU_NAME]),
        category=clean(row[CATEGORY]) or None,
        sales_amount=to_int(row[SALES]),
        quantity=to_int(row[QUANTITY]),
    )
    # row[DAILY_AVG] (일평균매출액)은 파생값이라 저장하지 않는다


def _verify_unique_codes(sales: list[MenuSale]) -> None:
    """
    menu_sales의 PK가 (store, date, menu) 이므로 중복 코드가 있으면 적재에서 덮어써진다.
    중첩표를 잘못 골랐을 때 나타나는 증상이기도 하다.
    """
    seen: set[str] = set()
    duplicated = {s.menu_code for s in sales if s.menu_code in seen or seen.add(s.menu_code)}
    if duplicated:
        raise ParseError(f"메뉴코드가 중복됐습니다 (표 선택 오류 가능): {sorted(duplicated)}")
