"""
DB 연결 — 기본은 조회용.

연결과 방언 처리는 `collector/db/`가 전부 한다. 이 모듈은 그것을 서버 쪽으로
끌어오는 얇은 층이며, **기본이 조회라는 의도**를 이름으로 드러내는 데 의미가 있다.
스키마 정의와 매출 데이터 쓰기는 수집기 쪽 담당이다.

예외가 하나 있다 — `open_write_connection()`. 신메뉴 기준·수동 지정(FN-253)은
수집 결과가 아니라 **사장님이 화면에서 정하는 값**이라 대시보드가 주인이다.
`app_settings` / `menu_overrides` 두 테이블에만 쓴다. 매출 테이블은 건드리지 않는다.

의존 방향은 `server → collector.db → collector.config` 한 방향이다.

⚠ Neon은 5분 유휴 후 잠든다(scale-to-zero). 잠든 뒤 첫 요청은 1~3초 걸린다.
  커넥션을 오래 들고 있어도 Neon 쪽에서 끊으므로, 요청마다 새로 연결한다
  (`deps.get_connection`). 풀링은 Neon의 `-pooler` 주소가 서버 쪽에서 담당한다.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from collector.config import Settings
from collector.db import Session, connect, connect_readonly


@contextmanager
def open_connection(settings: Settings) -> Iterator[Session]:
    with connect_readonly(settings) as session:
        yield session


@contextmanager
def open_write_connection(settings: Settings) -> Iterator[Session]:
    """
    설정 저장용 (FN-253). 빠져나올 때 commit, 예외가 나면 rollback.

    조회용과 이름을 나눈 이유: 어떤 요청이 DB를 바꾸는지 라우터 시그니처만 보고
    알 수 있어야 하기 때문이다. `get_connection` 을 쓰는 핸들러는 쓰기를 할 수 없다
    (`connect_readonly` 가 commit 하지 않으므로 조용히 사라진다).
    """
    with connect(settings) as session:
        yield session


def rows(session: Session, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    return session.execute(sql, params).fetchall()


def one(session: Session, sql: str, params: Sequence[Any] = ()) -> Any | None:
    return session.execute(sql, params).fetchone()
