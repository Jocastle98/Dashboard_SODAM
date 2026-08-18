"""매출 서비스 — 명세(docs/02 5.2)의 응답 형태로 가공한다."""

from __future__ import annotations

import sqlite3
from datetime import date

from ..repository import sales as repo
from ..repository import system as system_repo
from .period import Period, change_rate, safe_divide

WEEKDAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"]  # strftime('%w') 순서


def summary(connection: sqlite3.Connection, store_id: int, period: Period) -> dict:
    """GET /api/summary — KPI 카드 4종과 직전 동일 기간 대비 증감 (FN-210)."""
    current = repo.period_totals(connection, store_id, *period.iso)
    previous_period = period.previous()
    previous = repo.period_totals(connection, store_id, *previous_period.iso)

    def block(totals) -> dict:
        return {
            "totalSales": totals.sales,
            "orderCount": totals.orders,
            "avgTicket": safe_divide(totals.sales, totals.orders),
            "dailyAvg": safe_divide(totals.sales, totals.business_days),
        }

    current_block, previous_block = block(current), block(previous)
    return {
        "period": {
            "from": period.date_from.isoformat(),
            "to": period.date_to.isoformat(),
            "businessDays": current.business_days,
        },
        "current": current_block,
        "previous": previous_block,
        "change": {
            key: change_rate(current_block[key], previous_block[key])
            for key in current_block
        },
        "lastUpdated": _last_updated(connection, store_id),
    }


def daily(connection: sqlite3.Connection, store_id: int, period: Period) -> dict:
    """
    GET /api/sales/daily.

    sales=null + isClosed=true  → 휴무
    sales=null + isClosed=false → 미수집 (행이 아예 없는 날)
    0으로 채우지 않는다 (FR-DASH-12).
    """
    found = {row["biz_date"]: row for row in repo.daily(connection, store_id, *period.iso)}

    data = []
    cursor = period.date_from
    while cursor <= period.date_to:
        iso = cursor.isoformat()
        row = found.get(iso)
        if row is None:
            data.append(_missing_day(iso, cursor))
        elif row["is_closed"]:
            data.append({**_missing_day(iso, cursor), "isClosed": True})
        else:
            data.append({
                "date": iso,
                "dayOfWeek": WEEKDAY_NAMES[int(cursor.strftime("%w"))],
                "sales": row["sales_amount"],
                "orders": row["order_count"],
                "avgTicket": safe_divide(row["sales_amount"], row["order_count"]),
                "isClosed": False,
            })
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return {"data": data}


def _missing_day(iso: str, day: date) -> dict:
    return {
        "date": iso,
        "dayOfWeek": WEEKDAY_NAMES[int(day.strftime("%w"))],
        "sales": None, "orders": None, "avgTicket": None, "isClosed": False,
    }


def weekday(connection: sqlite3.Connection, store_id: int, period: Period) -> dict:
    """GET /api/sales/weekday — 월~일 순서로 돌려준다 (화면 순서와 일치)."""
    by_index = {row["weekday"]: row for row in repo.by_weekday(connection, store_id, *period.iso)}

    data = []
    for index in [1, 2, 3, 4, 5, 6, 0]:  # 월화수목금토일
        row = by_index.get(index)
        data.append({
            "dayOfWeek": WEEKDAY_NAMES[index],
            "avgSales": int(row["avg_sales"]) if row else None,
            "avgOrders": int(row["avg_orders"]) if row else None,
            "sampleDays": row["sample_days"] if row else 0,
        })
    return {"data": data}


def hourly(connection: sqlite3.Connection, store_id: int, period: Period) -> dict:
    """
    GET /api/sales/hourly.
    데이터가 없으면 available=false — 화면은 위젯을 숨긴다 (FN-240, TC-13).
    """
    rows = repo.by_hour(connection, store_id, *period.iso)
    data = [{"hour": row["hour"], "sales": row["sales"], "orders": row["orders"]}
            for row in rows if row["sales"]]

    peak_hours = [item["hour"] for item in sorted(data, key=lambda x: -x["sales"])[:3]]
    return {
        "available": bool(data),
        "data": data,
        "peakHours": sorted(peak_hours),
    }


def heatmap(connection: sqlite3.Connection, store_id: int, period: Period) -> dict:
    """요일×시간 히트맵 (FN-240 토글 / 공모전 보완 1순위)."""
    rows = repo.weekday_hour_matrix(connection, store_id, *period.iso)
    return {
        "available": bool(rows),
        "data": [
            {"dayOfWeek": WEEKDAY_NAMES[row["weekday"]], "hour": row["hour"],
             "avgSales": int(row["avg_sales"])}
            for row in rows
        ],
    }


def _last_updated(connection: sqlite3.Connection, store_id: int) -> str | None:
    row = system_repo.last_collection(connection, store_id)
    return row["finished_at"] if row else None
