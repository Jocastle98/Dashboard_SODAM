"""매출 서비스 — 명세(docs/02 5.2)의 응답 형태로 가공한다."""

from __future__ import annotations

from datetime import date, timedelta

from ..repository import sales as repo
from ..repository import system as system_repo
from .period import Period, change_rate, safe_divide, week_of
from collector.db import Row, Session

WEEKDAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"]  # strftime('%w') 순서


def summary(session: Session, store_id: int, period: Period) -> dict:
    """GET /api/summary — KPI 카드 4종과 직전 동일 기간 대비 증감 (FN-210)."""
    current = repo.period_totals(session, store_id, *period.iso)
    previous_period = period.previous()
    previous = repo.period_totals(session, store_id, *previous_period.iso)

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
        "lastUpdated": _last_updated(session, store_id),
    }


def daily(session: Session, store_id: int, period: Period) -> dict:
    """
    GET /api/sales/daily.

    sales=null + isClosed=true  → 휴무
    sales=null + isClosed=false → 미수집 (행이 아예 없는 날)
    0으로 채우지 않는다 (FR-DASH-12).
    """
    found = {row["biz_date"]: row for row in repo.daily(session, store_id, *period.iso)}

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


def weekday(session: Session, store_id: int, period: Period) -> dict:
    """GET /api/sales/weekday — 월~일 순서로 돌려준다 (화면 순서와 일치)."""
    by_index = {row["weekday"]: row for row in repo.by_weekday(session, store_id, *period.iso)}

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


def weekly_compare(session: Session, store_id: int, period: Period) -> dict:
    """
    GET /api/sales/weekly-compare — 요일별 '이번 주 vs 지난 주' (FN-235 / FR-DASH-13).

    기준 주는 **기간 안에서 매출이 있는 마지막 날이 속한 월~일**이다.
    종료일을 그대로 쓰면 수집이 며칠 밀렸을 때 표가 통째로 비어 버린다
    (매일 수집되는 평소에는 종료일 = 어제이므로 결과가 같다).
    어느 주를 비교했는지는 화면에 날짜로 찍으므로 오해할 여지가 없다.

    합계는 **양쪽 다 매출이 있는 요일끼리만** 더한다. 이번 주가 아직 안 끝났을 때
    3일 합계와 7일 합계를 비교하면 사장님이 매출이 반토막 난 것으로 오해한다.
    """
    latest = repo.last_business_date(session, store_id, *period.iso)
    anchor = date.fromisoformat(latest) if latest else period.date_to
    this_week = week_of(anchor)
    last_week = this_week.shifted(-7)

    this_rows = _daily_by_date(session, store_id, this_week)
    last_rows = _daily_by_date(session, store_id, last_week)

    data = []
    for offset in range(7):
        this_day = this_week.date_from + timedelta(days=offset)
        last_day = last_week.date_from + timedelta(days=offset)
        this_block = _compare_day(this_day, this_rows.get(this_day.isoformat()))
        last_block = _compare_day(last_day, last_rows.get(last_day.isoformat()))
        data.append({
            "dayOfWeek": WEEKDAY_NAMES[int(this_day.strftime("%w"))],
            "thisWeek": this_block,
            "lastWeek": last_block,
            # 한쪽이라도 값이 없으면 증감을 내지 않는다 — 0원으로 치면 ▼100%가 된다
            "change": (
                change_rate(this_block["sales"], last_block["sales"])
                if this_block["sales"] is not None and last_block["sales"] is not None
                else None
            ),
        })

    paired = [row for row in data
              if row["thisWeek"]["sales"] is not None and row["lastWeek"]["sales"] is not None]
    this_total = sum(row["thisWeek"]["sales"] for row in paired)
    last_total = sum(row["lastWeek"]["sales"] for row in paired)

    return {
        "thisWeek": {"from": this_week.date_from.isoformat(), "to": this_week.date_to.isoformat()},
        "lastWeek": {"from": last_week.date_from.isoformat(), "to": last_week.date_to.isoformat()},
        "data": data,
        "total": {
            "pairedDays": len(paired),
            "thisWeekSales": this_total,
            "lastWeekSales": last_total,
            "change": change_rate(this_total, last_total) if paired else None,
        },
    }


def _daily_by_date(session: Session, store_id: int,
                   week: Period) -> dict[str, Row]:
    return {row["biz_date"]: row for row in repo.daily(session, store_id, *week.iso)}


def _compare_day(day: date, row: Row | None) -> dict:
    """
    sales=null + isClosed=true  → 휴무
    sales=null + isClosed=false → 미수집 또는 아직 오지 않은 날 (FR-DASH-12)
    """
    if row is None or row["is_closed"]:
        return {
            "date": day.isoformat(), "sales": None, "orders": None,
            "isClosed": bool(row is not None and row["is_closed"]),
        }
    return {
        "date": day.isoformat(),
        "sales": row["sales_amount"],
        "orders": row["order_count"],
        "isClosed": False,
    }


def hourly(session: Session, store_id: int, period: Period) -> dict:
    """
    GET /api/sales/hourly.
    데이터가 없으면 available=false — 화면은 위젯을 숨긴다 (FN-240, TC-13).
    """
    rows = repo.by_hour(session, store_id, *period.iso)
    data = [{"hour": row["hour"], "sales": row["sales"], "orders": row["orders"]}
            for row in rows if row["sales"]]

    peak_hours = [item["hour"] for item in sorted(data, key=lambda x: -x["sales"])[:3]]
    return {
        "available": bool(data),
        "data": data,
        "peakHours": sorted(peak_hours),
    }


def heatmap(session: Session, store_id: int, period: Period) -> dict:
    """요일×시간 히트맵 (FN-240 토글 / 공모전 보완 1순위)."""
    rows = repo.weekday_hour_matrix(session, store_id, *period.iso)
    return {
        "available": bool(rows),
        "data": [
            {"dayOfWeek": WEEKDAY_NAMES[row["weekday"]], "hour": row["hour"],
             "avgSales": int(row["avg_sales"])}
            for row in rows
        ],
    }


def _last_updated(session: Session, store_id: int) -> str | None:
    row = system_repo.last_collection(session, store_id)
    return row["finished_at"] if row else None
