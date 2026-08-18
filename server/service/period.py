"""
기간 계산 — 필터 해석과 '직전 동일 길이 기간' 산출.

KPI 증감률의 비교 기준이다 (FN-210). 여러 서비스가 같은 규칙을 써야 하므로
여기 한 곳에 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

MAX_RANGE_DAYS = 366 * 2  # FN-202 — 최대 조회 범위


@dataclass(frozen=True)
class Period:
    date_from: date
    date_to: date

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    @property
    def iso(self) -> tuple[str, str]:
        return self.date_from.isoformat(), self.date_to.isoformat()

    def previous(self) -> "Period":
        """직전 동일 길이 기간. 7일 조회면 그 앞 7일."""
        end = self.date_from - timedelta(days=1)
        return Period(end - timedelta(days=self.days - 1), end)


class InvalidPeriod(ValueError):
    """FN-202 — 종료일 < 시작일, 범위 초과 등."""


def parse_period(date_from: str, date_to: str) -> Period:
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except ValueError as error:
        raise InvalidPeriod("날짜 형식은 YYYY-MM-DD 여야 합니다.") from error

    if end < start:
        raise InvalidPeriod("종료일이 시작일보다 빠릅니다.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise InvalidPeriod(f"조회 범위는 최대 {MAX_RANGE_DAYS}일입니다.")
    return Period(start, end)


def change_rate(current: float, previous: float) -> float | None:
    """
    증감률 = (현재 − 이전) ÷ 이전 × 100, 소수 1자리.
    이전 기간 데이터가 없으면 None — 화면에서 "비교 데이터 없음"으로 표시한다.
    """
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def safe_divide(numerator: float, denominator: float) -> int:
    return int(numerator / denominator) if denominator else 0
