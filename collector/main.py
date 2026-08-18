"""
수집기 진입점 — 조율만 한다. 로직은 service/repository/parse에 있다.

사용:
    python -m collector.main --init                # DB 스키마 적용
    python -m collector.main --days 7              # 최근 7일 (검증용)
    python -m collector.main --from 2026-08-01 --to 2026-08-15
    python -m collector.main --backfill            # 과거 BACKFILL_MONTHS개월
    python -m collector.main --yesterday           # 전일 (스케줄러가 호출)
    python -m collector.main --status              # 적재 현황만 확인
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import repository as repo  # noqa: E402
from collector.auth import PosLoginError, create_session  # noqa: E402
from collector.config import Settings  # noqa: E402
from collector.logutil import enable_utf8_output, log, section  # noqa: E402
from collector.pos_client import PosClient  # noqa: E402
from collector.service import Collector  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POS 매출 수집기")
    parser.add_argument("--init", action="store_true", help="DB 스키마 적용 후 종료")
    parser.add_argument("--status", action="store_true", help="적재 현황만 출력하고 종료")
    parser.add_argument("--days", type=int, help="최근 N일 수집 (오늘 제외)")
    parser.add_argument("--yesterday", action="store_true", help="전일만 수집 (FR-COL-01)")
    parser.add_argument("--backfill", action="store_true",
                        help="과거 BACKFILL_MONTHS개월 수집 (FR-COL-03)")
    parser.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    return parser.parse_args()


def resolve_period(args: argparse.Namespace, settings: Settings) -> tuple[date, date]:
    yesterday = date.today() - timedelta(days=1)

    if args.date_from:
        start = date.fromisoformat(args.date_from)
        end = date.fromisoformat(args.date_to) if args.date_to else yesterday
    elif args.days:
        start, end = yesterday - timedelta(days=args.days - 1), yesterday
    elif args.backfill:
        start, end = yesterday - timedelta(days=30 * settings.backfill_months), yesterday
    else:  # --yesterday 및 기본값
        start = end = yesterday

    if end < start:
        raise SystemExit(f"종료일이 시작일보다 빠릅니다: {start} ~ {end}")
    return start, end


def print_status(connection, store_id: int) -> None:
    section("적재 현황")
    first, last = repo.date_range_in_db(connection, store_id)
    log(f"  기간: {first or '(없음)'} ~ {last or '(없음)'}")
    for table in ("orders", "daily_sales", "hourly_sales", "menus", "menu_sales",
                  "order_cancels", "collection_logs"):
        log(f"  {table:16} {repo.count_rows(connection, table):>8,} 행")


def main() -> int:
    enable_utf8_output()
    args = parse_args()
    settings = Settings.load()

    with repo.connect(settings) as connection:
        repo.apply_schema(connection)
        store_id = repo.ensure_store(connection, settings)

        if args.init:
            log(f"스키마 적용 완료 → {repo.database_path(settings)}")
            return 0
        if args.status:
            print_status(connection, store_id)
            return 0

        start, end = resolve_period(args, settings)
        days = (end - start).days + 1
        section(f"수집 {start} ~ {end}  ({days}일)")
        log(f"  예상 요청 수: 주문 {_months(start, end)}회 + 취소 {_months(start, end)}회 "
            f"+ 메뉴 {days}회 ≈ {_months(start, end) * 2 + days}초")

        try:
            client = PosClient(settings, create_session(settings))
        except PosLoginError as error:
            log(f"\n{error}")
            return 1

        result = Collector(settings, client, connection).collect(start, end)

        section("결과")
        log(f"  주문 {result.orders:,}건 / 메뉴 {result.menu_rows:,}행 / 취소 {result.cancels:,}건")
        log(f"  일별 {result.daily:,}일 / 시간대 {result.hourly:,}행")
        if result.issues:
            log(f"  ⚠ 품질 경고 {len(result.issues)}건 (위 로그 참고)")
        if result.failures:
            log(f"  ✗ 실패 {len(result.failures)}건:")
            for failure in result.failures[:10]:
                log(f"     {failure}")
        print_status(connection, store_id)
        return 0 if result.ok else 2


def _months(start: date, end: date) -> int:
    from collector.service import month_chunks
    return len(month_chunks(start, end))


if __name__ == "__main__":
    raise SystemExit(main())
