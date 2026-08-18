"""
로그 출력과 비밀값 마스킹.

CLAUDE.md 보안 규칙: 로그에 쿠키·비밀번호를 출력하지 않는다.
비밀값을 찍어야 할 일이 생기면 반드시 mask()를 거친다.
"""

from __future__ import annotations

import sys


def enable_utf8_output() -> None:
    """
    Windows 기본 콘솔 코드페이지(cp949)로는 파이프/리다이렉트 시 한글이 깨진다.
    진입점에서 1회 호출한다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def mask(value: str | None, keep: int = 4) -> str:
    """앞 keep자만 남기고 가린다. keep=0이면 전부 가린다."""
    if not value:
        return "(없음)"
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)


def log(message: str = "") -> None:
    print(message, flush=True)


def section(title: str) -> None:
    log()
    log("=" * 68)
    log(f"  {title}")
    log("=" * 68)


def warn(message: str) -> None:
    log(f"  ⚠ {message}")


def fail(message: str) -> None:
    log(f"  ✗ {message}")
