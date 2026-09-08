"""
SQL 방언 처리 테스트 (`collector/db/dialect.py`).

**DB에 연결하지 않는다.** 문자열 변환 규칙만 고정한다.
이식 중 가장 조용히 틀리는 부분이라 여기서 못박아 둔다:

  · 요일 번호가 양쪽 다 **일요일=0** 이라는 것
    (`server/service/sales.py`의 `WEEKDAY_NAMES` 순서가 이 가정에 묶여 있다.
     어긋나면 화면은 정상으로 보이는데 숫자만 요일이 밀린다)
  · 자리표시자 변환이 **문자열 리터럴 안을 건드리지 않는다**는 것

실제 두 DB의 응답이 같은지는 tests/test_api.py 가 적재된 DB로 검증한다.
"""

from __future__ import annotations

import pytest

from collector.db import dialect as d


# ── 방언 판별 ──────────────────────────────────────────────

@pytest.mark.parametrize("url, expected", [
    ("sqlite:///./data/sodam.db", "sqlite"),
    ("sqlite:///C:/tmp/x.db", "sqlite"),
    ("postgresql://u:p@host/db", "postgres"),
    ("postgres://u:p@host/db", "postgres"),
    ("postgresql://u:p@host/db?sslmode=require", "postgres"),
])
def test_detects_dialect_from_url_prefix(url, expected):
    assert d.detect(url).name == expected


@pytest.mark.parametrize("url", ["", "mysql://u:p@host/db", "./data/sodam.db", "sqlite:/x.db"])
def test_unknown_url_fails_loudly(url):
    """조용히 SQLite 로 흘러가면 배포 환경에서 빈 화면이 나온다."""
    with pytest.raises(d.UnsupportedDatabase):
        d.detect(url)


def test_each_dialect_points_at_its_own_schema_file():
    assert d.SQLITE.schema_path.name == "schema.sql"
    assert d.POSTGRES.schema_path.name == "schema_pg.sql"
    assert d.SQLITE.schema_path.exists()
    assert d.POSTGRES.schema_path.exists()


# ── 요일 번호 ──────────────────────────────────────────────

def test_weekday_expressions_agree_on_sunday_zero():
    """
    양쪽 다 일요일=0 이어야 한다. 이 사실이 WEEKDAY_NAMES 순서의 근거다.
    표현식 자체는 다르지만 기준이 같다는 점을 문서화해 둔다.
    """
    assert "strftime('%w'" in d.SQLITE.weekday("biz_date")
    assert "EXTRACT(DOW FROM" in d.POSTGRES.weekday("biz_date")


def test_weekday_names_order_matches_sunday_zero():
    """서비스 쪽 상수가 일요일=0 가정을 지키고 있는지 함께 고정한다."""
    from server.service.sales import WEEKDAY_NAMES

    assert WEEKDAY_NAMES[0] == "일"
    assert WEEKDAY_NAMES[1] == "월"
    assert WEEKDAY_NAMES[6] == "토"


def test_postgres_weekday_casts_text_to_date():
    """biz_date 를 TEXT 로 두었으므로 캐스팅이 필요하다 (schema_pg.sql 머리말 참고)."""
    assert "::date" in d.POSTGRES.weekday("biz_date")


# ── 불리언 리터럴 ──────────────────────────────────────────

def test_boolean_literals_differ():
    """`WHERE is_closed = 0` 은 PostgreSQL 에서 타입 오류다."""
    assert (d.SQLITE.true, d.SQLITE.false) == ("1", "0")
    assert (d.POSTGRES.true, d.POSTGRES.false) == ("TRUE", "FALSE")


# ── 자리표시자 변환 ────────────────────────────────────────

def test_sqlite_leaves_sql_untouched():
    sql = "SELECT * FROM t WHERE a = ? AND b LIKE '%김%'"
    assert d.SQLITE.bind(sql) == sql


def test_postgres_converts_placeholders():
    assert d.POSTGRES.bind("SELECT * FROM t WHERE a = ? AND b = ?") == \
        "SELECT * FROM t WHERE a = %s AND b = %s"


def test_postgres_escapes_literal_percent():
    """psycopg 는 `%` 를 자기 자리표시자로 읽는다 — 원래 있던 `%` 는 `%%` 가 돼야 한다."""
    assert d.POSTGRES.bind("SELECT 50 % 7") == "SELECT 50 %% 7"


def test_postgres_does_not_touch_string_literals():
    """
    문자열 리터럴 안의 `?` 와 `%` 는 그대로 남아야 한다.
    통째로 replace 하면 `LIKE '%김%'` 이 망가진다.
    """
    result = d.POSTGRES.bind("SELECT * FROM t WHERE name LIKE '%김%' AND q = ? AND note = '왜?'")
    assert "'%김%'" in result
    assert "'왜?'" in result
    assert "q = %s" in result


def test_postgres_handles_doubled_quotes_inside_strings():
    """`''` 는 문자열 안의 인용부호 하나다 — 여기서 문자열이 끝났다고 보면 뒤가 다 어긋난다."""
    result = d.POSTGRES.bind("SELECT * FROM t WHERE a = 'it''s ?' AND b = ?")
    assert "'it''s ?'" in result
    assert "b = %s" in result


def test_conversion_count_matches_parameter_count():
    """실제 repository SQL 모양으로 개수를 확인한다."""
    sql = "INSERT INTO orders (a,b,c) VALUES (?,?,?) ON CONFLICT(a) DO UPDATE SET b=excluded.b"
    assert d.POSTGRES.bind(sql).count("%s") == 3
