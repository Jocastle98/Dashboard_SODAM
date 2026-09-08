"""메뉴 서비스 — 순위·ABC 등급·추이."""

from __future__ import annotations


from ..repository import menu as repo
from .menu_alias import display_name
from .period import Period
from collector.db import Session

ABC_A_THRESHOLD = 0.70   # 누적 매출 비중 70%까지 A
ABC_B_THRESHOLD = 0.90   # ~90% B, 나머지 C


def abc_grades(session: Session, store_id: int, period: Period) -> dict[str, str]:
    """
    ABC 등급은 **전체 메뉴**의 누적 비중으로 정한다.
    TOP 10만 놓고 계산하면 등급이 실제보다 후해진다.
    """
    rows = repo.all_shares(session, store_id, *period.iso)
    total = sum(row["sales"] for row in rows)
    if not total:
        return {}

    grades: dict[str, str] = {}
    cumulative = 0
    for row in rows:
        cumulative += row["sales"]
        share = cumulative / total
        grades[row["menu_code"]] = (
            "A" if share <= ABC_A_THRESHOLD else "B" if share <= ABC_B_THRESHOLD else "C"
        )
    return grades


def ranking(session: Session, store_id: int, period: Period,
            limit: int = 10, sort_by: str = "sales") -> dict:
    """GET /api/menu/ranking — 순위·비중·ABC·전기간 대비 순위 변동 (FN-250)."""
    rows = repo.ranking(session, store_id, *period.iso, limit, sort_by)
    total = repo.total_sales(session, store_id, *period.iso)
    grades = abc_grades(session, store_id, period)
    previous_ranks = _previous_ranks(session, store_id, period, sort_by)

    data = []
    for index, row in enumerate(rows, start=1):
        previous_rank = previous_ranks.get(row["menu_code"])
        data.append({
            "rank": index,
            "menuCode": row["menu_code"],
            # POS 원본 이름 대신 표시명을 쓴다 (FN-251)
            "menuName": display_name(row["menu_code"], row["menu_name"]),
            "category": row["category"],
            "quantity": row["quantity"],
            "sales": row["sales"],
            "share": round(row["sales"] / total * 100, 1) if total else 0.0,
            "abcGrade": grades.get(row["menu_code"], "C"),
            # 이전 기간에 없던 메뉴는 null — 0(변동없음)과 구분한다
            "rankChange": (previous_rank - index) if previous_rank else None,
        })

    return {"totalSales": total, "data": data}


def _previous_ranks(session: Session, store_id: int,
                    period: Period, sort_by: str) -> dict[str, int]:
    rows = repo.ranking(session, store_id, *period.previous().iso, 100, sort_by)
    return {row["menu_code"]: index for index, row in enumerate(rows, start=1)}


def trend(session: Session, store_id: int,
          menu_code: str, period: Period) -> dict | None:
    """GET /api/menu/{menuCode}/trend — 메뉴 상세 화면(FN-301)."""
    name = repo.find_name(session, store_id, menu_code)
    if name is None:
        return None
    rows = repo.trend(session, store_id, menu_code, *period.iso)
    return {
        "menuCode": menu_code,
        "menuName": display_name(menu_code, name),
        "data": [
            {"date": row["biz_date"], "quantity": row["quantity"], "sales": row["sales_amount"]}
            for row in rows
        ],
    }
