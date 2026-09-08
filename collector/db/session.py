"""
커넥션 래퍼 — repository가 방언을 몰라도 되게 만든다.

`repository`는 `?` 자리표시자로 SQL을 쓰고 `row["컬럼"]`으로 읽는다.
그 인터페이스를 SQLite와 PostgreSQL 양쪽에서 똑같이 성립시키는 것이 이 모듈의 일이다.

  · 자리표시자 변환은 `dialect.bind()`에 맡긴다 — 규칙을 두 벌 두지 않는다.
  · `executescript()`는 SQLite에만 있다. PostgreSQL은 파라미터 없는 `execute()`가 대신한다.
  · 방언별 SQL 조각이 필요한 repository는 `connection.dialect`로 물어본다
    (`connection.dialect.weekday("biz_date")`). 전역 상태를 두지 않기 위함이다.

`row["컬럼"]` 접근은 드라이버 쪽에서 맞춘다 — SQLite는 `sqlite3.Row`,
psycopg는 `dict_row`. 둘 다 이름으로 읽히고 `dict(row)`도 된다.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .dialect import Dialect


class Session:
    """
    DB-API 커넥션 하나를 감싼다.

    `execute` / `executemany` / `commit` / `rollback` / `close` 만 노출한다.
    드라이버 고유 기능이 필요하면 `raw`로 꺼내 쓰되, 그런 코드는 방언에 묶인다는 뜻이다.
    """

    def __init__(self, raw: Any, dialect: Dialect):
        self.raw = raw
        self.dialect = dialect

    # ── 질의 ────────────────────────────────────────────
    def execute(self, sql: str, params: Sequence[Any] | None = None):
        statement = self.dialect.bind(sql)
        if params is None:
            return self.raw.execute(statement)
        return self.raw.execute(statement, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]):
        """
        `sqlite3.Connection`은 `executemany` 지름길을 주지만 **psycopg는 커서에만 있다.**
        그 차이를 여기서 흡수한다 — repository가 알아야 할 일이 아니다.
        """
        batch = [tuple(row) for row in rows]
        if not batch:
            return None                     # 빈 배치에 executemany를 부르지 않는다

        statement = self.dialect.bind(sql)
        if hasattr(self.raw, "executemany"):
            return self.raw.executemany(statement, batch)
        with self.raw.cursor() as cursor:
            cursor.executemany(statement, batch)
        return None

    def executescript(self, script: str) -> None:
        """
        여러 문장을 한 번에. 파라미터는 받지 않는다 — 스키마 적용 전용이다.
        `dialect.bind()`를 거치지 않는다: 스키마 SQL에는 자리표시자가 없고,
        `datetime('now')` 같은 방언 고유 표현이 그대로 있어야 한다.
        """
        if self.dialect.runs_scripts_natively:
            self.raw.executescript(script)
        else:
            self.raw.execute(script)

    # ── 트랜잭션 ────────────────────────────────────────
    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    def __repr__(self) -> str:              # 비밀값이 섞이지 않게 방언만 보여준다
        return f"<Session {self.dialect.name}>"
