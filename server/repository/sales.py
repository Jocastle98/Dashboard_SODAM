"""매출 조회 — 일별 / 요일별 / 시간대별 / 기간 합계."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PeriodTotals:
    sales: int
    orders: int
    business_days: int   # 휴무일 제외한 영업일수


def period_totals(connection: sqlite3.Connection, store_id: int,
                  date_from: str, date_to: str) -> PeriodTotals:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(sales_amount), 0) AS sales,
               COALESCE(SUM(order_count), 0)  AS orders,
               COUNT(*)                       AS days
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ? AND is_closed = 0
        """,
        (store_id, date_from, date_to),
    ).fetchone()
    return PeriodTotals(sales=row["sales"], orders=row["orders"], business_days=row["days"])


def daily(connection: sqlite3.Connection, store_id: int,
          date_from: str, date_to: str) -> list[sqlite3.Row]:
    """
    수집한 날만 행이 나온다. 미수집일은 행 자체가 없어야 한다 —
    0원으로 채우면 사장님이 매출 0으로 오해한다 (FR-DASH-12).
    """
    return connection.execute(
        """
        SELECT biz_date, sales_amount, order_count, is_closed
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        ORDER BY biz_date
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def by_weekday(connection: sqlite3.Connection, store_id: int,
               date_from: str, date_to: str) -> list[sqlite3.Row]:
    """휴무일은 평균에서 제외한다 (FN-230)."""
    return connection.execute(
        """
        SELECT CAST(strftime('%w', biz_date) AS INTEGER) AS weekday,
               AVG(sales_amount) AS avg_sales,
               AVG(order_count)  AS avg_orders,
               COUNT(*)          AS sample_days
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ? AND is_closed = 0
        GROUP BY weekday
        ORDER BY weekday
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def by_hour(connection: sqlite3.Connection, store_id: int,
            date_from: str, date_to: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT hour,
               COALESCE(SUM(sales_amount), 0) AS sales,
               COALESCE(SUM(order_count), 0)  AS orders
        FROM hourly_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        GROUP BY hour
        ORDER BY hour
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def weekday_hour_matrix(connection: sqlite3.Connection, store_id: int,
                        date_from: str, date_to: str) -> list[sqlite3.Row]:
    """요일×시간 히트맵 (공모전 보완 1순위). 시간대 데이터가 날짜별로 있어 가능하다."""
    return connection.execute(
        """
        SELECT CAST(strftime('%w', biz_date) AS INTEGER) AS weekday,
               hour,
               AVG(sales_amount) AS avg_sales
        FROM hourly_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        GROUP BY weekday, hour
        ORDER BY weekday, hour
        """,
        (store_id, date_from, date_to),
    ).fetchall()
