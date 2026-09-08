"""
매출 조회 — 일별 / 요일별 / 시간대별 / 기간 합계.

방언이 갈리는 곳이 둘 있다. 둘 다 `session.dialect`에 물어본다 —
규칙을 여기 적어 두면 `collector/db/dialect.py`와 어긋난다.

  · 불리언 리터럴 : `is_closed = 0` (SQLite) / `= FALSE` (PostgreSQL)
  · 요일 번호     : `strftime('%w', ...)` / `EXTRACT(DOW FROM ...)`  — 양쪽 다 일요일=0
"""

from __future__ import annotations

from dataclasses import dataclass

from collector.db import Session


@dataclass(frozen=True)
class PeriodTotals:
    sales: int
    orders: int
    business_days: int   # 휴무일 제외한 영업일수


def period_totals(session: Session, store_id: int,
                  date_from: str, date_to: str) -> PeriodTotals:
    row = session.execute(
        """
        SELECT COALESCE(SUM(sales_amount), 0) AS sales,
               COALESCE(SUM(order_count), 0)  AS orders,
               COUNT(*)                       AS days
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ? AND is_closed = {false}
        """.format(false=session.dialect.false),
        (store_id, date_from, date_to),
    ).fetchone()
    return PeriodTotals(sales=row["sales"], orders=row["orders"], business_days=row["days"])


def daily(session: Session, store_id: int,
          date_from: str, date_to: str) -> list:
    """
    수집한 날만 행이 나온다. 미수집일은 행 자체가 없어야 한다 —
    0원으로 채우면 사장님이 매출 0으로 오해한다 (FR-DASH-12).
    """
    return session.execute(
        """
        SELECT biz_date, sales_amount, order_count, is_closed
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        ORDER BY biz_date
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def last_business_date(session: Session, store_id: int,
                       date_from: str, date_to: str) -> str | None:
    """기간 안에서 매출이 있는 마지막 날. FN-235의 '이번 주' 기준점이다."""
    row = session.execute(
        """
        SELECT MAX(biz_date) AS biz_date
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ?
          AND is_closed = {false} AND sales_amount > 0
        """.format(false=session.dialect.false),
        (store_id, date_from, date_to),
    ).fetchone()
    return row["biz_date"] if row and row["biz_date"] else None


def by_weekday(session: Session, store_id: int,
               date_from: str, date_to: str) -> list:
    """휴무일은 평균에서 제외한다 (FN-230)."""
    return session.execute(
        """
        SELECT {weekday} AS weekday,
               AVG(sales_amount) AS avg_sales,
               AVG(order_count)  AS avg_orders,
               COUNT(*)          AS sample_days
        FROM daily_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ? AND is_closed = {false}
        GROUP BY 1
        ORDER BY 1
        """.format(weekday=session.dialect.weekday("biz_date"),
                   false=session.dialect.false),
        (store_id, date_from, date_to),
    ).fetchall()


def by_hour(session: Session, store_id: int,
            date_from: str, date_to: str) -> list:
    return session.execute(
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


def weekday_hour_matrix(session: Session, store_id: int,
                        date_from: str, date_to: str) -> list:
    """요일×시간 히트맵 (공모전 보완 1순위). 시간대 데이터가 날짜별로 있어 가능하다."""
    return session.execute(
        """
        SELECT {weekday} AS weekday,
               hour,
               AVG(sales_amount) AS avg_sales
        FROM hourly_sales
        WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        GROUP BY 1, hour
        ORDER BY 1, hour
        """.format(weekday=session.dialect.weekday("biz_date")),
        (store_id, date_from, date_to),
    ).fetchall()
