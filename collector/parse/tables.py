"""
표 선택과 값 정규화 — 세 파서가 공유하는 단일 출처.

여기 담긴 규칙은 모두 실측으로 확인한 것이다 (docs/03, docs/05).
파서마다 따로 구현하면 한쪽만 고쳐져 조용히 어긋난다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..formats import Table, decode_korean, extract_tables


class ParseError(ValueError):
    """응답이 예상한 표 구조가 아니다 — 조용히 빈 결과를 돌려주지 않는다."""


# ── 표 선택 ────────────────────────────────────────────────
# ⚠ 파서의 첫 번째 규칙.
# POS 응답은 <table>이 중첩되어 있어, 모든 표의 행을 합치면 데이터가 정확히 2배가 된다.
# 오류가 나지 않고 매출만 2배가 되므로 반드시 표 하나만 골라 써야 한다.
#
# 주문 리포트 실측 구조:
#   [0] 3행 x 1열     제목/기간/출력일자
#   [1] 2행 x 20열    헤더 (중첩)
#   [2] 1행 x 19열    헤더 (중첩)
#   [3] 52행 x 970열  중첩표가 이어붙은 것 — 버린다
#   [4] 51행 x 19열   진짜 데이터

@dataclass(frozen=True)
class Report:
    """리포트 하나에서 뽑아낸 헤더와 데이터 행."""

    header: list[str] | None
    rows: list[list[str]]


def select_report(html: str, width: int, header_label: str) -> Report:
    """
    목표 열 수와 일치하는 행을 가진 표 중 **행이 가장 많은 것 하나**를 데이터 표로 고른다.

    헤더는 데이터 표에 없을 수 있다 — 주문 리포트는 헤더가 별도 중첩표에 들어 있고
    데이터 표는 합계 행부터 시작한다. 그래서 헤더는 표 전체에서 따로 찾는다.
    """
    tables = extract_tables(html)
    candidates = [table for table in tables if any(len(row) == width for row in table)]
    if not candidates:
        raise ParseError(
            f"{width}열짜리 표를 찾지 못했습니다. "
            f"발견한 표: {[(len(t), max((len(r) for r in t), default=0)) for t in tables]}"
        )

    # 열 수가 맞는 행이 가장 많은 표를 데이터 표로 본다.
    # (전체 행 수로 고르면 중첩 래퍼 표가 뽑힐 수 있다)
    best = max(candidates, key=lambda table: sum(1 for row in table if len(row) == width))
    rows = _deduplicate([row for row in best if len(row) == width])

    header = next(
        (row for table in tables for row in table
         if len(row) == width and clean(row[0]) == header_label),
        None,
    )
    return Report(header=header, rows=rows)


def _deduplicate(rows: list[list[str]]) -> list[list[str]]:
    """
    똑같은 행이 두 번 잡히면 매출이 그대로 2배가 된다 — 오류 없이 숫자만 커진다.
    표 선택이 잘못되더라도 여기서 한 번 더 막는다.

    안전한 이유: 주문 행은 주문번호가, 메뉴 행은 메뉴코드가, 취소 행은 순번(No.)이
    각각 달라서 서로 다른 데이터가 완전히 동일한 행이 될 수 없다.
    """
    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []
    for row in rows:
        key = tuple(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def select_rows(html: str, width: int) -> list[list[str]]:
    """데이터 행만 필요할 때. 헤더 검증이 필요하면 select_report를 쓴다."""
    return select_report(html, width, "").rows


def verify_header(header: list[str] | None, expected: tuple[str, ...]) -> None:
    """
    컬럼 순서가 바뀌면 값이 엉뚱한 자리에 들어간다. 조용히 넘어가지 않는다.
    헤더를 아예 못 찾은 것도 구조 변경 신호다.
    """
    if header is None:
        raise ParseError(f"헤더 행({expected[0]})을 찾지 못했습니다.")
    actual = tuple(clean(cell) for cell in header[:len(expected)])
    if actual != expected:
        raise ParseError(f"컬럼 구성이 바뀌었습니다.\n  기대: {expected}\n  실제: {actual}")


def select_rows_from_bytes(content: bytes, width: int) -> list[list[str]]:
    """응답 바이트에서 바로 행을 뽑는다. euc-kr/UTF-8 혼재는 decode_korean이 처리한다."""
    return select_rows(decode_korean(content), width)


def is_data_row(row: list[str]) -> bool:
    """
    헤더 행과 합계 행을 걸러낸다.
    첫 칸이 순번(숫자)인 행만 데이터다. 합계 행은 순번이 `0`으로 온다.
    """
    head = row[0].strip()
    return head.isdigit() and head != "0"


def find_total_row(rows: list[list[str]]) -> list[str] | None:
    """합계 행(첫 칸 `0`). 검증용으로만 쓰고 적재하지 않는다."""
    return next((row for row in rows if row[0].strip() == "0"), None)


# ── 값 정규화 ──────────────────────────────────────────────

_NUMBER_NOISE = re.compile(r"[,\s원]")


def to_int(text: str | None) -> int:
    """
    `'3,175,900'` → `3175900`.
    빈 칸은 0. 음수는 취소 건일 수 있으므로 부호를 살린다 (DQ-01).
    """
    if text is None:
        return 0
    cleaned = _NUMBER_NOISE.sub("", text.strip())
    if not cleaned or cleaned in ("-", "."):
        return 0
    try:
        return int(float(cleaned))
    except ValueError as error:
        raise ParseError(f"숫자로 읽을 수 없습니다: {text!r}") from error


def clean(text: str | None) -> str:
    """공백 정리. 빈 문자열은 그대로 빈 문자열."""
    return re.sub(r"\s+", " ", text).strip() if text else ""


def optional(text: str | None) -> str | None:
    """빈 칸을 NULL로 저장하기 위한 변환."""
    value = clean(text)
    return value or None


# ── 날짜 / 시각 ────────────────────────────────────────────

_ORDER_NO_DIGITS = re.compile(r"\D")


def normalize_order_no(text: str) -> str:
    """
    주문번호를 리포트 간 동일한 형식으로 맞춘다.
    주문 리포트는 `202608150001`, 취소 리포트는 `20260815-0043` 으로 준다.
    """
    digits = _ORDER_NO_DIGITS.sub("", clean(text))
    if len(digits) < 8:
        raise ParseError(f"주문번호 형식이 예상과 다릅니다: {text!r}")
    return digits


def biz_date_from_order_no(order_no: str) -> str:
    """주문번호 앞 8자가 영업일자다. `'202608150001'` → `'2026-08-15'`."""
    digits = normalize_order_no(order_no)
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


_DATETIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})")
_TIME_ONLY = re.compile(r"^(\d{1,2}):(\d{2})")


def to_datetime(text: str | None) -> str | None:
    """`'2026-08-15 11:02'` → 그대로 표준화. 형식이 다르면 None."""
    match = _DATETIME.search(clean(text))
    if not match:
        return None
    year, month, day, hour, minute = match.groups()
    return f"{year}-{month}-{day} {hour}:{minute}"


def to_datetime_on(biz_date: str, text: str | None) -> str | None:
    """
    시각만 오는 리포트(취소 내역의 `18:05`)를 영업일자와 합쳐 표준화한다.
    이미 날짜가 붙어 있으면 그대로 쓴다.
    """
    full = to_datetime(text)
    if full:
        return full
    match = _TIME_ONLY.match(clean(text))
    if not match:
        return None
    hour, minute = match.groups()
    return f"{biz_date} {int(hour):02d}:{minute}"


def hour_of(timestamp: str | None) -> int | None:
    """`'2026-08-15 11:02'` → `11`."""
    if not timestamp or len(timestamp) < 13:
        return None
    try:
        return int(timestamp[11:13])
    except ValueError:
        return None
