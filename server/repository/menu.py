"""메뉴 조회 — 순위 / 추이."""

from __future__ import annotations

from collector.db import Row, Session


# 정렬 기준 + **동점 처리**.
#
# tie-break 가 없으면 DB·실행계획에 따라 동점 메뉴의 순서가 달라진다.
# 육수·반반 같은 옵션 메뉴는 sales=0 이라 동점이 대량으로 생기므로,
# "수량순 TOP 10"이 새로고침마다 흔들리고 rankChange 도 엉뚱하게 나온다.
# menu_code 로 마지막을 못박아 어느 DB에서든 같은 순서가 나오게 한다.
SORT_ORDERS = {
    "sales":    "sales DESC, quantity DESC, m.menu_code ASC",
    "quantity": "quantity DESC, sales DESC, m.menu_code ASC",
}


def ranking(session: Session, store_id: int,
            date_from: str, date_to: str, limit: int, sort_by: str) -> list[Row]:
    order_by = SORT_ORDERS.get(sort_by, SORT_ORDERS["sales"])
    return session.execute(
        f"""
        SELECT m.menu_code, m.menu_name, m.category,
               SUM(ms.quantity)     AS quantity,
               SUM(ms.sales_amount) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND ms.biz_date BETWEEN ? AND ?
        GROUP BY m.menu_id
        ORDER BY {order_by}
        LIMIT ?
        """,
        (store_id, date_from, date_to, limit),
    ).fetchall()


def total_sales(session: Session, store_id: int,
                date_from: str, date_to: str) -> int:
    row = session.execute(
        """
        SELECT COALESCE(SUM(sales_amount), 0) AS total
        FROM menu_sales WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        """,
        (store_id, date_from, date_to),
    ).fetchone()
    return int(row["total"])


def all_shares(session: Session, store_id: int,
               date_from: str, date_to: str) -> list[Row]:
    """
    ABC 등급은 전체 메뉴의 누적 비중으로 정한다 — TOP 10만 봐서는 계산할 수 없다.

    tie-break 를 명시한다: 누적 순서가 등급 경계를 결정하므로, 동점 메뉴의
    순서가 흔들리면 경계에 걸친 메뉴의 등급이 실행마다 A↔B 로 바뀐다.
    """
    return session.execute(
        """
        SELECT m.menu_code, SUM(ms.sales_amount) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND ms.biz_date BETWEEN ? AND ?
        GROUP BY m.menu_id
        ORDER BY sales DESC, m.menu_code ASC
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def trend(session: Session, store_id: int, menu_code: str,
          date_from: str, date_to: str) -> list[Row]:
    return session.execute(
        """
        SELECT ms.biz_date, ms.quantity, ms.sales_amount
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND m.menu_code = ? AND ms.biz_date BETWEEN ? AND ?
        ORDER BY ms.biz_date
        """,
        (store_id, menu_code, date_from, date_to),
    ).fetchall()


def find_name(session: Session, store_id: int, menu_code: str) -> str | None:
    row = session.execute(
        "SELECT menu_name FROM menus WHERE store_id = ? AND menu_code = ?",
        (store_id, menu_code),
    ).fetchone()
    return row["menu_name"] if row else None
