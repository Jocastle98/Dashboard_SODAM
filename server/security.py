"""
비밀번호 해시와 세션 — 인증 원시요소만 담당한다.

CLAUDE.md 보안 규칙:
  · 비밀번호는 bcrypt 해시로만 저장 (FR-AUTH-04)
  · 세션은 HttpOnly 쿠키. 응답 본문에 계정 정보를 싣지 않는다
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

SESSION_COOKIE = "sodam_session"
SESSION_MAX_AGE = 12 * 60 * 60          # FR-AUTH-06 — 12시간
REMEMBER_MAX_AGE = 30 * 24 * 60 * 60    # FR-AUTH-07 — 30일

LOCKOUT_THRESHOLD = 5                   # FR-AUTH-05 — 5회 실패
LOCKOUT_SECONDS = 5 * 60                # 5분 차단


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False  # 해시 형식이 깨진 경우 — 인증 실패로 취급


class SessionCodec:
    """서명된 세션 토큰. 사용자 식별자만 담고 그 외 정보는 넣지 않는다."""

    def __init__(self, secret: str):
        if not secret:
            raise ValueError("SESSION_SECRET이 비어 있습니다. .env를 확인하세요.")
        self._signer = TimestampSigner(secret)

    def issue(self, username: str) -> str:
        return self._signer.sign(username.encode("utf-8")).decode("ascii")

    def read(self, token: str, max_age: int = REMEMBER_MAX_AGE) -> str | None:
        try:
            return self._signer.unsign(token, max_age=max_age).decode("utf-8")
        except (BadSignature, SignatureExpired):
            return None


@dataclass
class LoginThrottle:
    """
    FR-AUTH-05 — 5회 실패 시 5분 차단.
    단일 매장·소수 사용자 전제이므로 메모리에 둔다 (ASM-03).
    """

    failures: dict[str, list[float]] = field(default_factory=dict)

    def retry_after(self, username: str) -> int:
        attempts = self._recent(username)
        if len(attempts) < LOCKOUT_THRESHOLD:
            return 0
        return max(0, int(LOCKOUT_SECONDS - (time.time() - attempts[-LOCKOUT_THRESHOLD])))

    def record_failure(self, username: str) -> None:
        self.failures.setdefault(username, []).append(time.time())

    def clear(self, username: str) -> None:
        self.failures.pop(username, None)

    def _recent(self, username: str) -> list[float]:
        cutoff = time.time() - LOCKOUT_SECONDS
        recent = [at for at in self.failures.get(username, []) if at > cutoff]
        self.failures[username] = recent
        return recent
