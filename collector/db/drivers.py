"""
실제 커넥션 생성. 드라이버 고유 설정이 여기 모여 있다.

`dialect.py`는 "무엇이 다른지"를, 이 모듈은 "어떻게 붙는지"를 안다.

**PostgreSQL 쪽 설정 두 가지는 반드시 유지할 것:**

  `prepare_threshold=None`
      Neon의 풀링 주소(`...-pooler...`)는 PgBouncer 트랜잭션 모드다.
      psycopg는 같은 질의를 5번 실행하면 prepared statement로 바꾸는데,
      트랜잭션 모드에서는 그것이 다음 세션에서 사라져 있어 실패한다.
      끄면 매번 보내지만 안전하다.

  `row_factory=dict_row`
      SQLite의 `sqlite3.Row`처럼 `row["컬럼"]`으로 읽히게 한다.
      기본값(tuple)로 두면 repository의 모든 조회가 깨진다.
"""

from __future__ import annotations

from pathlib import Path

from ..config import ROOT
from .dialect import POSTGRES, SQLITE, Dialect
from .session import Session

CONNECT_TIMEOUT_SEC = 15        # Neon은 5분 유휴 후 잠든다 — 첫 요청에 콜드스타트가 붙는다


def sqlite_path(database_url: str) -> Path:
    """`sqlite:///./data/sodam.db` → 실제 파일 경로."""
    raw = database_url[len("sqlite:///"):]
    path = Path(raw)
    return path if path.is_absolute() else (ROOT / raw).resolve()


def open_sqlite(database_url: str) -> Session:
    import sqlite3

    path = sqlite_path(database_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return Session(connection, SQLITE)


def open_postgres(database_url: str) -> Session:
    import psycopg
    from psycopg.rows import dict_row

    connection = psycopg.connect(
        database_url,
        prepare_threshold=None,     # PgBouncer 트랜잭션 모드 대응 (위 설명 참고)
        row_factory=dict_row,
        connect_timeout=CONNECT_TIMEOUT_SEC,
    )
    return Session(connection, POSTGRES)


def open_session(dialect: Dialect, database_url: str) -> Session:
    return open_postgres(database_url) if dialect.is_postgres else open_sqlite(database_url)
