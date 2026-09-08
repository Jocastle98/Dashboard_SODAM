"""
수집 파이프라인 — 조회·파싱·집계·적재를 순서대로 엮는다.

수집 계획 (docs/05 1장):
  주문·취소 : 월 단위 요청  (기간 내 전체 행을 돌려주므로 12개월이 12회)
  메뉴      : 일 단위 요청  (기간을 주면 합산돼서 나와 일별 분해가 불가)
  시간대    : 요청하지 않음 (주문의 판매시간에서 유도)

요청 간 1초 대기와 재시도는 PosClient가 처리한다. 여기서 sleep하지 않는다.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import repository as repo
from .aggregate import (
    QualityIssue,
    aggregate_daily,
    aggregate_hourly,
    check_menu_consistency,
    check_payment_sums,
)
from .config import Settings
from .formats import decode_korean
from .logutil import log, warn
from .parse import parse_cancels, parse_menu, parse_orders
from .parse.tables import ParseError
from .pos_client import PosClient
from .db import Session

DATE_FORMAT = "%Y%m%d"


@dataclass
class CollectResult:
    orders: int = 0
    menu_rows: int = 0
    cancels: int = 0
    daily: int = 0
    hourly: int = 0
    failures: list[str] = field(default_factory=list)
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """기간을 달력 월 단위로 자른다. 월 경계를 넘는 요청은 응답이 지나치게 커진다."""
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        last_day = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        chunks.append((cursor, min(last_day, end)))
        cursor = last_day + timedelta(days=1)
    return chunks


def each_day(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


class Collector:
    def __init__(self, settings: Settings, client: PosClient, session: Session):
        self.settings = settings
        self.client = client
        self.session = session
        self.store_id = repo.ensure_store(session, settings)

    # ── 공개 진입점 ─────────────────────────────────────
    def collect(self, start: date, end: date) -> CollectResult:
        result = CollectResult()

        orders = self._collect_orders(start, end, result)
        cancels = self._collect_cancels(start, end, result)
        menu_total_by_date = self._collect_menu(start, end, result)

        self._aggregate(orders, cancels, start, end, result)
        self._check_quality(orders, menu_total_by_date, start, end, result)
        return result

    # ── 리포트별 수집 ───────────────────────────────────
    def _collect_orders(self, start: date, end: date, result: CollectResult):
        collected = []
        for chunk_start, chunk_end in month_chunks(start, end):
            label = f"{chunk_start} ~ {chunk_end}"
            log(f"  주문   {label}")
            orders = self._fetch_parse(
                "orders", chunk_start, chunk_end, result,
                lambda content: parse_orders(decode_korean(content)).orders,
            )
            if orders is None:
                continue
            result.orders += repo.upsert_orders(self.session, self.store_id, orders)
            collected.extend(orders)
            log(f"         {len(orders)}건")
        return collected

    def _collect_cancels(self, start: date, end: date, result: CollectResult):
        collected = []
        for chunk_start, chunk_end in month_chunks(start, end):
            log(f"  취소   {chunk_start} ~ {chunk_end}")
            cancels = self._fetch_parse(
                "cancels", chunk_start, chunk_end, result,
                lambda content: parse_cancels(decode_korean(content)),
            )
            if cancels is None:
                continue
            result.cancels += repo.upsert_cancels(self.session, self.store_id, cancels)
            collected.extend(cancels)
        return collected

    def _collect_menu(self, start: date, end: date, result: CollectResult) -> dict[str, int]:
        """메뉴는 하루씩 조회한다. 기간을 주면 합산돼 일별로 분해할 수 없다."""
        totals: dict[str, int] = {}
        days = each_day(start, end)
        for index, day in enumerate(days, start=1):
            if index % 10 == 1 or index == len(days):
                log(f"  메뉴   {day}  ({index}/{len(days)})")
            iso = day.isoformat()
            sales = self._fetch_parse(
                "menu", day, day, result,
                lambda content, iso=iso: parse_menu(decode_korean(content), iso),
            )
            if sales is None:
                continue
            result.menu_rows += repo.upsert_menu_sales(self.session, self.store_id, sales)
            totals[iso] = sum(s.sales_amount for s in sales)
        return totals

    # ── 조회 + 파싱 공통 ────────────────────────────────
    def _fetch_parse(self, report_type: str, start: date, end: date, result: CollectResult, parse):
        """
        조회·파싱·원본보존·로그를 한 곳에서 처리한다.
        실패는 예외로 터뜨리지 않고 기록한 뒤 다음 기간으로 넘어간다 (부분 성공 허용).
        """
        date_from, date_to = start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)
        entry = repo.CollectionLog(
            store_id=self.store_id, report_type=report_type,
            started_at=repo.now(), target_from=date_from, target_to=date_to,
        )
        fetch = {
            "orders": self.client.fetch_orders,
            "menu": self.client.fetch_menu,
            "cancels": self.client.fetch_cancels,
        }[report_type]

        try:
            response = fetch(date_from, date_to)
            if response.status_code >= 400:
                raise ParseError(f"HTTP {response.status_code}")
            repo.save_raw_file(self.session, self.store_id, report_type,
                               date_from, date_to, response.content)
            parsed = parse(response.content)
        except Exception as error:  # noqa: BLE001 — 한 기간 실패가 전체를 멈추면 안 된다
            message = f"{report_type} {date_from}~{date_to}: {type(error).__name__}: {error}"
            result.failures.append(message)
            warn(message)
            repo.write_log(self.session, entry, "failed", 0, str(error))
            return None

        repo.write_log(self.session, entry, "success", len(parsed))
        return parsed

    # ── 집계 ────────────────────────────────────────────
    def _aggregate(self, orders, cancels, start: date, end: date, result: CollectResult) -> None:
        covered = self._successfully_covered_days(start, end)
        daily = aggregate_daily(orders, cancels, covered_dates=covered)
        hourly = aggregate_hourly(orders)

        result.daily = repo.upsert_daily(self.session, self.store_id, daily)
        result.hourly = repo.replace_hourly(
            self.session, self.store_id, hourly, [d.biz_date for d in daily]
        )

    def _successfully_covered_days(self, start: date, end: date) -> list[str]:
        """
        주문 수집에 성공한 기간에 속한 날짜들.
        DQ-02(휴무 판정)는 '수집에 성공했는데 주문이 0건'이라는 사실에 근거한다.
        수집 자체가 실패한 날을 휴무로 기록하면 안 된다.
        """
        rows = self.session.execute(
            """
            SELECT target_from, target_to FROM collection_logs
            WHERE store_id = ? AND report_type = 'orders' AND status = 'success'
            """,
            (self.store_id,),
        ).fetchall()

        covered: set[str] = set()
        for row in rows:
            chunk_start = _parse_compact(row["target_from"])
            chunk_end = _parse_compact(row["target_to"])
            for day in each_day(max(chunk_start, start), min(chunk_end, end)):
                covered.add(day.isoformat())
        return sorted(covered)

    # ── 품질 검증 ───────────────────────────────────────
    def _check_quality(self, orders, menu_total_by_date, start, end, result) -> None:
        daily = aggregate_daily(orders)
        result.issues.extend(check_menu_consistency(daily, menu_total_by_date))
        result.issues.extend(check_payment_sums(orders))
        for issue in result.issues:
            warn(f"[{issue.rule}] {issue.biz_date} {issue.message}")


def _parse_compact(text: str) -> date:
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
