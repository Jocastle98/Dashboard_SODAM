"""
신메뉴 라우터 (FN-252 / FN-253).

조율만 한다 — 판정 규칙과 기본값은 전부 `service/new_menu.py` 에 있다.

`data.py` 가 아니라 따로 둔 이유: 여기에만 **쓰기** 엔드포인트가 있다.
한 파일에 섞으면 어떤 요청이 DB를 바꾸는지 읽어 내기 어려워진다.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status

from ..deps import (_error, current_user, get_connection, get_store_id,
                    get_write_connection, get_write_store_id, period_param)
from ..service import new_menu as service
from ..service.new_menu import InvalidCriteria, UnknownMenu
from ..service.period import Period
from collector.db import Session

router = APIRouter(prefix="/api/menu/new", tags=["new-menu"],
                   dependencies=[Depends(current_user)])


@router.get("")
def new_menu(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """기간 내 신메뉴 판매량·매출 (FN-252)."""
    return service.evaluate(session, store_id, period)


@router.get("/catalog")
def new_menu_catalog(
    period: Period = Depends(period_param),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """수동 지정 패널용 — 전체 메뉴 + 첫 판매일 + 자동/수동 판정 (FN-253)."""
    return service.catalog(session, store_id, period)


@router.put("/settings")
def save_settings(
    period: Period = Depends(period_param),
    payload: dict = Body(...),
    session: Session = Depends(get_write_connection),
    store_id: int = Depends(get_write_store_id),
):
    """
    신메뉴 기준 저장 (FN-253).

    `{"mode": "months", "months": 3}` 또는 `{"mode": "since", "since": "2026-05-01"}`.

    기간(`from`/`to`)을 함께 받는 이유: `months` 는 **조회 기간 종료일** 기준으로
    기준일을 계산하므로, 저장 직후 돌려줄 `since` 를 뽑으려면 종료일이 필요하다.
    """
    try:
        criteria = service.save_criteria(session, store_id, payload, period.date_to)
    except InvalidCriteria as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error("INVALID_PARAM", str(error)),
        ) from error
    return {"success": True, "criteria": criteria.as_dict()}


@router.put("/overrides/{menu_code}")
def save_override(
    menu_code: str,
    payload: dict = Body(...),
    session: Session = Depends(get_write_connection),
    store_id: int = Depends(get_write_store_id),
):
    """
    메뉴 하나를 신메뉴로 지정하거나 제외한다 (FN-253).

    `{"isNew": true}` 지정 / `{"isNew": false}` 제외 / `{"isNew": null}` 해제(자동 판정).
    """
    is_new = payload.get("isNew", None) if isinstance(payload, dict) else None
    if is_new is not None and not isinstance(is_new, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error("INVALID_PARAM", "isNew 는 true / false / null 이어야 합니다."),
        )

    try:
        service.set_override(session, store_id, menu_code, is_new)
    except UnknownMenu as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error("NOT_FOUND", "없는 메뉴입니다."),
        ) from error
    return {"success": True, "menuCode": menu_code, "isNew": is_new}
