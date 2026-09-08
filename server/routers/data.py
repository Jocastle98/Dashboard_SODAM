"""
데이터 조회 라우터 (docs/02 5.2).

모든 엔드포인트가 인증을 요구한다 (NFR-SEC-04).
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import _error, current_user, get_connection, get_store_id, period_param
from ..service import menu as menu_service
from ..service import sales as sales_service
from ..service import system as system_service
from ..service.period import Period
from collector.db import Session

router = APIRouter(prefix="/api", tags=["data"], dependencies=[Depends(current_user)])


@router.get("/summary")
def summary(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.summary(session, store_id, period)


@router.get("/sales/daily")
def sales_daily(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.daily(session, store_id, period)


@router.get("/sales/weekday")
def sales_weekday(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.weekday(session, store_id, period)


@router.get("/sales/weekly-compare")
def sales_weekly_compare(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """요일별 이번 주 vs 지난 주 (FN-235). 기준 주는 기간 종료일이 속한 월~일."""
    return sales_service.weekly_compare(session, store_id, period)


@router.get("/sales/hourly")
def sales_hourly(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.hourly(session, store_id, period)


@router.get("/sales/heatmap")
def sales_heatmap(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """요일×시간 히트맵 — 인력 배치 판단용 (공모전 보완 1순위)."""
    return sales_service.heatmap(session, store_id, period)


@router.get("/menu/ranking")
def menu_ranking(
    period: Period = Depends(period_param),
    limit: int = Query(default=10, ge=1, le=100),
    sort_by: str = Query(default="sales", alias="sortBy", pattern="^(sales|quantity)$"),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return menu_service.ranking(session, store_id, period, limit, sort_by)


@router.get("/menu/{menu_code}/trend")
def menu_trend(
    menu_code: str,
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    result = menu_service.trend(session, store_id, menu_code, period)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error("NOT_FOUND", "데이터를 찾을 수 없습니다."),
        )
    return result


@router.get("/system/status")
def system_status(
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return system_service.status(session, store_id)


@router.get("/system/collections")
def system_collections(
    limit: int = Query(default=30, ge=1, le=200),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """FN-501 — 관리자 화면의 수집 이력."""
    return system_service.collection_history(session, store_id, limit)
