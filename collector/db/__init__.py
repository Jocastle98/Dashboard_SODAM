"""
DB 연결의 공개 창구.

SQLite(로컬·오프라인)와 PostgreSQL(Neon 배포)을 같은 코드로 쓴다.
어느 쪽인지는 `DATABASE_URL` 접두사가 결정한다.

    sqlite:///./data/sodam.db     → SQLite
    postgresql://...              → PostgreSQL

사용:

    from collector.db import connect, apply_schema, now

    with connect(settings) as session:
        apply_schema(session)
        session.execute("SELECT * FROM daily_sales WHERE store_id = ?", (1,))

책임 분리:

    dialect.py   무엇이 다른지 (자리표시자·불리언·요일함수·스키마파일)
    drivers.py   어떻게 붙는지 (sqlite3 / psycopg 고유 설정)
    session.py   repository가 쓰는 인터페이스를 방언과 무관하게 만드는 래퍼
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from ..config import Settings
from .dialect import POSTGRES, SQLITE, Dialect, UnsupportedDatabase, detect
from .drivers import open_session, sqlite_path
from .session import Session

# 조회 결과 한 행. SQLite 는 `sqlite3.Row`, psycopg 는 `dict` 를 준다 —
# 둘 다 `row["컬럼"]` 으로 읽히고 `dict(row)` 도 된다. 타입 힌트에서는 구분하지 않는다.
Row = Any

__all__ = [
    "Session", "Row", "Dialect", "SQLITE", "POSTGRES", "UnsupportedDatabase",
    "connect", "connect_readonly", "apply_schema", "dialect_of", "now",
    "sqlite_path", "describe_target",
]


def dialect_of(settings: Settings) -> Dialect:
    return detect(settings.database_url)


@contextmanager
def connect(settings: Settings) -> Iterator[Session]:
    """쓰기용. 블록을 정상적으로 빠져나오면 commit, 예외가 나면 rollback."""
    session = open_session(dialect_of(settings), settings.database_url)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def connect_readonly(settings: Settings) -> Iterator[Session]:
    """
    조회용. commit하지 않는다.

    PostgreSQL에서는 조회만 해도 트랜잭션이 열리므로 나올 때 rollback으로 닫는다.
    그대로 두면 Neon 쪽에 idle-in-transaction 커넥션이 쌓인다.
    """
    session = open_session(dialect_of(settings), settings.database_url)
    try:
        yield session
    finally:
        try:
            session.rollback()
        finally:
            session.close()


def apply_schema(session: Session) -> None:
    """방언에 맞는 스키마 파일을 적용한다. 이미 있으면 아무 일도 없다 (IF NOT EXISTS)."""
    session.executescript(session.dialect.schema_path.read_text(encoding="utf-8"))


def describe_target(settings: Settings) -> str:
    """
    연결 대상을 사람이 읽을 형태로. **비밀값을 넣지 않는다.**

    로그·CLI 출력에 쓰이므로 계정과 비밀번호가 섞이면 안 된다
    (CLAUDE.md 보안 규칙: 로그에 쿠키·비밀번호를 출력하지 않는다).
    """
    dialect = dialect_of(settings)
    if not dialect.is_postgres:
        return f"SQLite {sqlite_path(settings.database_url)}"

    # postgresql://user:pw@host/db?... → host/db 만 남긴다
    remainder = settings.database_url.split("://", 1)[1]
    location = remainder.split("@")[-1].split("?")[0]
    return f"PostgreSQL {location}"


def now() -> str:
    """
    시각 문자열의 **단일 출처**. `2026-09-08T23:41:36+09:00`

    DB의 DEFAULT(`datetime('now')` / `NOW()`)를 쓰지 않는다.
    SQLite의 `datetime('now')`는 UTC·공백구분·오프셋없음으로 이 형식과 달라서,
    같은 DB 안에 두 가지 형식이 섞여 있었다. 형식을 여기 한 곳에서만 정한다.
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
