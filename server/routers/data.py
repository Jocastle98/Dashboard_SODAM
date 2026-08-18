"""
데이터 조회 라우터 (docs/02 5.2).

모든 엔드포인트가 인증을 요구한다 (NFR-SEC-04).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import _error, current_user, get_connection, get_store_id, period_param
from ..service import menu as menu_service
from ..service import sales as sales_service
from ..service import system as system_service
from ..service.period import Period

router = APIRouter(prefix="/api", tags=["data"], dependencies=[Depends(current_user)])


@router.get("/summary")
def summary(
    period: Period = Depends(period_param),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.summary(connection, store_id, period)


@router.get("/sales/daily")
def sales_daily(
    period: Period = Depends(period_param),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.daily(connection, store_id, period)


@router.get("/sales/weekday")
def sales_weekday(
    period: Period = Depends(period_param),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.weekday(connection, store_id, period)


@router.get("/sales/hourly")
def sales_hourly(
    period: Period = Depends(period_param),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return sales_service.hourly(connection, store_id, period)


@router.get("/sales/heatmap")
def sales_heatmap(
    period: Period = Depends(period_param),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """요일×시간 히트맵 — 인력 배치 판단용 (공모전 보완 1순위)."""
    return sales_service.heatmap(connection, store_id, period)


@router.get("/menu/ranking")
def menu_ranking(
    period: Period = Depends(period_param),
    limit: int = Query(default=10, ge=1, le=100),
    sort_by: str = Query(default="sales", alias="sortBy", pattern="^(sales|quantity)$"),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return menu_service.ranking(connection, store_id, period, limit, sort_by)


@router.get("/menu/{menu_code}/trend")
def menu_trend(
    menu_code: str,
    period: Period = Depends(period_param),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    result = menu_service.trend(connection, store_id, menu_code, period)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error("NOT_FOUND", "데이터를 찾을 수 없습니다."),
        )
    return result


@router.get("/system/status")
def system_status(
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    return system_service.status(connection, store_id)


@router.get("/system/collections")
def system_collections(
    limit: int = Query(default=30, ge=1, le=200),
    connection: sqlite3.Connection = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """FN-501 — 관리자 화면의 수집 이력."""
    return system_service.collection_history(connection, store_id, limit)
