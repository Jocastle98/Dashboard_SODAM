"""
공통 의존성 — 설정·DB·현재 사용자·기간 파싱.

라우터가 이것들을 조합만 하면 되도록 여기 모은다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from fastapi import Cookie, Depends, HTTPException, Query, status

from collector.config import Settings
from collector.db import Row, Session

from .db import open_connection, open_write_connection
from .repository import system as system_repo
from .repository import users as user_repo
from .security import SESSION_COOKIE, LoginThrottle, SessionCodec
from .service.period import InvalidPeriod, Period, parse_period


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


@lru_cache(maxsize=1)
def get_session_codec() -> SessionCodec:
    return SessionCodec(get_settings().session_secret)


@lru_cache(maxsize=1)
def get_throttle() -> LoginThrottle:
    return LoginThrottle()


def get_connection() -> Iterator[Session]:
    with open_connection(get_settings()) as session:
        yield session


def get_write_connection() -> Iterator[Session]:
    """
    쓰기용 커넥션 (FN-253 신메뉴 설정 전용).

    `get_connection` 과 나눠 둔다 — 라우터 시그니처만 보고 그 요청이 DB를
    바꾸는지 알 수 있어야 한다. 이유는 `server/db.py` 의 주석에 있다.
    """
    with open_write_connection(get_settings()) as session:
        yield session


def get_store_id(session: Session = Depends(get_connection)) -> int:
    return _resolve_store_id(session)


def get_write_store_id(session: Session = Depends(get_write_connection)) -> int:
    """
    쓰기 요청용 매장 ID. **조회용과 같은 커넥션을 쓴다.**

    `get_store_id` 를 그대로 쓰면 쓰기 요청 하나가 커넥션을 둘 연다 —
    Neon 은 잠들었다 깨는 데 1~3초가 걸리므로 그 값이 두 배가 된다.
    FastAPI 가 한 요청 안에서 같은 의존성을 캐시하므로, 라우터가
    `get_write_connection` 을 함께 받으면 커넥션은 하나다.
    """
    return _resolve_store_id(session)


def _resolve_store_id(session: Session) -> int:
    store_id = system_repo.store_id_by_code(session, get_settings().store_code)
    if store_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("NO_DATA", "아직 수집된 데이터가 없습니다."),
        )
    return store_id


def current_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_connection),
) -> Row:
    """미인증 요청은 401 (NFR-SEC-04). 프론트는 이때 로그인 화면으로 보낸다 (FN-263)."""
    username = get_session_codec().read(session_cookie) if session_cookie else None
    user = user_repo.find_by_username(session, username) if username else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("UNAUTHORIZED", "로그인이 필요합니다."),
        )
    return user


def period_param(
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
) -> Period:
    try:
        return parse_period(date_from, date_to)
    except InvalidPeriod as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error("INVALID_PARAM", str(error)),
        ) from error


def _error(code: str, message: str) -> dict:
    """docs/02 5.3 공통 오류 형식."""
    return {"code": code, "message": message}
