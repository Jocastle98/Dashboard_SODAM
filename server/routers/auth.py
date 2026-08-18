"""인증 라우터 (docs/02 5.1)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ..deps import _error, current_user, get_connection, get_session_codec, get_settings, get_throttle
from ..repository import system as system_repo
from ..repository import users as user_repo
from ..security import REMEMBER_MAX_AGE, SESSION_COOKIE, SESSION_MAX_AGE, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    connection: sqlite3.Connection = Depends(get_connection),
):
    throttle = get_throttle()

    retry_after = throttle.retry_after(payload.username)
    if retry_after:  # FR-AUTH-05
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={**_error("TOO_MANY_ATTEMPTS", f"{retry_after // 60 + 1}분 후 다시 시도해주세요."),
                    "retryAfter": retry_after},
        )

    user = user_repo.find_by_username(connection, payload.username)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        throttle.record_failure(payload.username)
        # FN-105 — 사유를 세분화하지 않는다 (계정 열거 방지)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("AUTH_FAILED", "아이디 또는 비밀번호가 올바르지 않습니다."),
        )

    throttle.clear(payload.username)
    user_repo.touch_login(connection, user["user_id"])

    max_age = REMEMBER_MAX_AGE if payload.remember else SESSION_MAX_AGE  # FR-AUTH-07
    response.set_cookie(
        SESSION_COOKIE,
        get_session_codec().issue(user["username"]),
        max_age=max_age,
        httponly=True,      # 스크립트에서 읽을 수 없게 (NFR-SEC-03)
        samesite="lax",
        secure=False,       # 배포 시 HTTPS에서 True (NFR-SEC-01)
    )
    return {"success": True, "user": _user_block(connection, user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"success": True}


@router.get("/session")
def session(
    user: sqlite3.Row = Depends(current_user),
    connection: sqlite3.Connection = Depends(get_connection),
):
    """FN-108 — 진입 시 유효 세션이면 대시보드로 바로 보낸다."""
    return {"authenticated": True, "user": _user_block(connection, user)}


def _user_block(connection: sqlite3.Connection, user: sqlite3.Row) -> dict:
    """응답에 비밀번호 해시나 POS 계정이 실리지 않게 필요한 필드만 담는다."""
    store = system_repo.store_info(connection, user["store_id"])
    return {
        "username": user["username"],
        "role": user["role"],
        "storeName": store["store_name"] if store else get_settings().store_name,
    }
