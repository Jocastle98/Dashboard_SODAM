"""메뉴 조회 — 순위 / 추이."""

from __future__ import annotations

import sqlite3

SORT_COLUMNS = {"sales": "sales", "quantity": "quantity"}


def ranking(connection: sqlite3.Connection, store_id: int,
            date_from: str, date_to: str, limit: int, sort_by: str) -> list[sqlite3.Row]:
    order_column = SORT_COLUMNS.get(sort_by, "sales")
    return connection.execute(
        f"""
        SELECT m.menu_code, m.menu_name, m.category,
               SUM(ms.quantity)     AS quantity,
               SUM(ms.sales_amount) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND ms.biz_date BETWEEN ? AND ?
        GROUP BY m.menu_id
        ORDER BY {order_column} DESC
        LIMIT ?
        """,
        (store_id, date_from, date_to, limit),
    ).fetchall()


def total_sales(connection: sqlite3.Connection, store_id: int,
                date_from: str, date_to: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(sales_amount), 0) AS total
        FROM menu_sales WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        """,
        (store_id, date_from, date_to),
    ).fetchone()
    return int(row["total"])


def all_shares(connection: sqlite3.Connection, store_id: int,
               date_from: str, date_to: str) -> list[sqlite3.Row]:
    """ABC 등급은 전체 메뉴의 누적 비중으로 정한다 — TOP 10만 봐서는 계산할 수 없다."""
    return connection.execute(
        """
        SELECT m.menu_code, SUM(ms.sales_amount) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND ms.biz_date BETWEEN ? AND ?
        GROUP BY m.menu_id
        ORDER BY sales DESC
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def trend(connection: sqlite3.Connection, store_id: int, menu_code: str,
          date_from: str, date_to: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT ms.biz_date, ms.quantity, ms.sales_amount
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND m.menu_code = ? AND ms.biz_date BETWEEN ? AND ?
        ORDER BY ms.biz_date
        """,
        (store_id, menu_code, date_from, date_to),
    ).fetchall()


def find_name(connection: sqlite3.Connection, store_id: int, menu_code: str) -> str | None:
    row = connection.execute(
        "SELECT menu_name FROM menus WHERE store_id = ? AND menu_code = ?",
        (store_id, menu_code),
    ).fetchone()
    return row["menu_name"] if row else None
