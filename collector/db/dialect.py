"""
SQL 방언 차이의 **단일 출처**.

SQLite(로컬 개발·오프라인 스냅샷)와 PostgreSQL(Neon 배포)을 같은 코드로 쓴다.
둘의 차이가 `collector/repository.py`와 `server/repository/`에 흩어지면
한쪽만 고쳐져서 조용히 어긋난다 — `formats.py`가 인코딩 함정을 한곳에 모은 것과 같은 이유다.

**이 모듈은 DB에 연결하지 않는다.** 무엇이 다른지만 안다. 연결은 `drivers.py`가 한다.

차이 목록:

| | SQLite | PostgreSQL |
|---|---|---|
| 자리표시자 | `?` | `%s` |
| 불리언 | `0` / `1` | `FALSE` / `TRUE` |
| 요일 번호 | `strftime('%w', d)` | `EXTRACT(DOW FROM d::date)` |
| 여러 문장 실행 | `executescript()` | `execute()` (파라미터 없을 때) |
| 스키마 파일 | `db/schema.sql` | `db/schema_pg.sql` |

**요일 번호는 양쪽 다 일요일=0이다.** 우연이 아니라 확인한 사실이며,
`server/service/sales.py`의 `WEEKDAY_NAMES` 순서가 이 가정에 묶여 있다.
바꾸면 화면은 정상으로 보이는데 숫자만 요일이 밀린다. `tests/test_dialect.py`가 고정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import ROOT

SCHEMA_DIR = ROOT / "db"

SQLITE_PREFIX = "sqlite:///"
POSTGRES_PREFIXES = ("postgresql://", "postgres://")


class UnsupportedDatabase(ValueError):
    """`DATABASE_URL`을 해석할 수 없다."""


@dataclass(frozen=True)
class Dialect:
    """한 방언이 어떻게 다른지. 값만 들고 있고 부작용이 없다."""

    name: str                       # 'sqlite' | 'postgres'
    placeholder: str                # 파라미터 자리표시자
    true: str                       # 불리언 참 리터럴
    false: str                       # 불리언 거짓 리터럴
    schema_file: str
    runs_scripts_natively: bool     # executescript()를 쓸 수 있나

    @property
    def is_postgres(self) -> bool:
        return self.name == "postgres"

    @property
    def schema_path(self) -> Path:
        return SCHEMA_DIR / self.schema_file

    def weekday(self, column: str) -> str:
        """
        요일 번호를 뽑는 식. **일요일=0** 기준이며 양쪽이 일치한다.

        PostgreSQL 쪽에 `::date` 캐스팅이 붙는 이유: `biz_date`를 TEXT로 두었기 때문이다.
        DATE로 바꾸면 조회 결과가 `datetime.date`로 나와, ISO 문자열을 키로 쓰는
        서비스 코드(`{row["biz_date"]: row}`)가 조용히 어긋난다.
        """
        if self.is_postgres:
            return f"EXTRACT(DOW FROM {column}::date)::int"
        return f"CAST(strftime('%w', {column}) AS INTEGER)"

    def bind(self, sql: str) -> str:
        """
        SQL의 자리표시자를 이 방언에 맞게 바꾼다.

        `?`를 그대로 두는 SQLite에서는 아무것도 하지 않는다. PostgreSQL에서는
        **문자열 리터럴 밖의 `?`만** `%s`로 바꾸고, 원래 있던 `%`는 `%%`로 escape한다
        (psycopg가 `%`를 자기 자리표시자로 읽기 때문).
        """
        if not self.is_postgres:
            return sql
        return _to_pyformat(sql)


SQLITE = Dialect(
    name="sqlite",
    placeholder="?",
    true="1",
    false="0",
    schema_file="schema.sql",
    runs_scripts_natively=True,
)

POSTGRES = Dialect(
    name="postgres",
    placeholder="%s",
    true="TRUE",
    false="FALSE",
    schema_file="schema_pg.sql",
    runs_scripts_natively=False,
)


def detect(database_url: str) -> Dialect:
    """`DATABASE_URL` 접두사로 방언을 고른다."""
    url = (database_url or "").strip()
    if url.startswith(SQLITE_PREFIX):
        return SQLITE
    if url.startswith(POSTGRES_PREFIXES):
        return POSTGRES
    raise UnsupportedDatabase(
        f"DATABASE_URL 을 해석할 수 없습니다: {url!r}\n"
        f"  sqlite:///./data/sodam.db  또는  postgresql://... 형식이어야 합니다."
    )


def _to_pyformat(sql: str) -> str:
    """
    `?` → `%s`, `%` → `%%`. 단 **단일 인용부호 안은 건드리지 않는다.**

    SQL 문자열 리터럴에 `?`나 `%`가 들어 있을 수 있다(예: `LIKE '%김%'`).
    통째로 replace하면 그것까지 망가진다.
    """
    out: list[str] = []
    in_string = False
    index = 0

    while index < len(sql):
        char = sql[index]

        if in_string:
            out.append(char)
            if char == "'":
                # '' 는 문자열 안의 인용부호 하나 — 아직 문자열 안이다
                if index + 1 < len(sql) and sql[index + 1] == "'":
                    out.append("'")
                    index += 2
                    continue
                in_string = False
            index += 1
            continue

        if char == "'":
            in_string = True
            out.append(char)
        elif char == "?":
            out.append("%s")
        elif char == "%":
            out.append("%%")
        else:
            out.append(char)
        index += 1

    return "".join(out)
