"""
수동 수집 라우터 (FN-205 / FR-COL-07).

조율만 한다 — 누가 어떻게 수집하는지는 `server/collect_trigger.py`가 안다.
여기서 하는 일은 트리거 예외를 docs/02 5.3 오류 형식으로 옮기는 것뿐이다.

읽기 전용 조회(`/api/system/status` 등)는 `routers/data.py`에 있다.
이 파일에는 **POS에 실제로 요청을 유발하는 엔드포인트만** 둔다.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, status

from collector.config import Settings

from .. import collect_trigger
from ..deps import _error, current_user, get_connection, get_settings, get_store_id
from collector.db import Session

router = APIRouter(prefix="/api/system", tags=["system"],
                   dependencies=[Depends(current_user)])


@router.get("/collect/status")
def collect_status(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """버튼을 어떻게 그릴지 판단할 근거. 화면이 수집 중에 3초마다 물어본다."""
    return collect_trigger.state(settings, session, store_id).as_dict()


@router.post("/collect")
def collect_now(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_connection),
    store_id: int = Depends(get_store_id),
):
    """
    지금 POS에서 수집한다.

    거절도 정상 동작이다 — POS에 요청이 겹쳐 나가지 않게 막는 것이 목적이다.
      409 이미 수집 중
      429 최소 간격 안 (Retry-After 헤더로 남은 시간을 알려준다)
      503 이 환경에는 트리거할 수단이 없다
    """
    try:
        return collect_trigger.trigger(settings, session, store_id).as_dict()
    except collect_trigger.TooSoon as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_error("TOO_SOON", str(error)),
            headers={"Retry-After": str(error.retry_after_sec)},
        ) from error
    except collect_trigger.AlreadyRunning as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error("ALREADY_RUNNING", str(error)),
        ) from error
    except collect_trigger.Unavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("UNAVAILABLE", str(error)),
        ) from error
    except collect_trigger.TriggerError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error("TRIGGER_FAILED", str(error)),
        ) from error
