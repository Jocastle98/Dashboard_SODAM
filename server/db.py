"""
DB 연결 — 조회용.

연결과 방언 처리는 `collector/db/`가 전부 한다. 이 모듈은 그것을 서버 쪽으로
끌어오는 얇은 층이며, **조회 전용이라는 의도**를 이름으로 드러내는 데 의미가 있다.
스키마 정의와 쓰기는 수집기 쪽 담당이다.

의존 방향은 `server → collector.db → collector.config` 한 방향이다.

⚠ Neon은 5분 유휴 후 잠든다(scale-to-zero). 잠든 뒤 첫 요청은 1~3초 걸린다.
  커넥션을 오래 들고 있어도 Neon 쪽에서 끊으므로, 요청마다 새로 연결한다
  (`deps.get_connection`). 풀링은 Neon의 `-pooler` 주소가 서버 쪽에서 담당한다.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from collector.config import Settings
from collector.db import Session, connect_readonly


@contextmanager
def open_connection(settings: Settings) -> Iterator[Session]:
    with connect_readonly(settings) as session:
        yield session


def rows(session: Session, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    return session.execute(sql, params).fetchall()


def one(session: Session, sql: str, params: Sequence[Any] = ()) -> Any | None:
    return session.execute(sql, params).fetchone()
