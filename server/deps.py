"""
공통 의존성 — 설정·DB·현재 사용자·기간 파싱.

라우터가 이것들을 조합만 하면 되도록 여기 모은다.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Iterator

from fastapi import Cookie, Depends, HTTPException, Query, status

from collector.config import Settings

from .db import open_connection
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


def get_connection() -> Iterator[sqlite3.Connection]:
    with open_connection(get_settings()) as connection:
        yield connection


def get_store_id(connection: sqlite3.Connection = Depends(get_connection)) -> int:
    store_id = system_repo.store_id_by_code(connection, get_settings().store_code)
    if store_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("NO_DATA", "아직 수집된 데이터가 없습니다."),
        )
    return store_id


def current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    connection: sqlite3.Connection = Depends(get_connection),
) -> sqlite3.Row:
    """미인증 요청은 401 (NFR-SEC-04). 프론트는 이때 로그인 화면으로 보낸다 (FN-263)."""
    username = get_session_codec().read(session) if session else None
    user = user_repo.find_by_username(connection, username) if username else None
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
