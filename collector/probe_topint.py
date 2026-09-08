"""
POS(탑아이앤티) 응답 실측 프로브 — STEP 1 진입점.

이 스크립트의 목적은 코드를 늘리는 것이 아니라 **POS 응답의 실체를 파악**하는 것이다.
확인 항목 (docs/00_진행가이드.md STEP 1):
  1. 응답의 실제 파일 포맷 (HTML table인가, 진짜 xls인가)   → formats.sniff_format
  2. 기간 조회 동작 — 7일을 주면 7행인가, 합계 1행인가       → probe_report
  3. 과거 소급 가능 범위                                     → probe_report
  4. 표의 실제 컬럼 구성 (하나도 빠짐없이)                    → probe_report
  5. 메뉴별/시간대별 정보 포함 여부                           → probe_report

여기서는 조율만 한다. 실제 로직은 모듈에 있다:
  config.py         .env 로딩
  pos_client.py     요청·재시도·1초 대기
  formats.py        포맷 판별·euc-kr 디코딩·표 추출
  probe_observer.py 관측
  probe_report.py   해석·분기 판단

사용:
    python -m collector.probe_topint            # 전체 프로브
    python -m collector.probe_topint --quick    # 포맷/컬럼만 (소급 프로브 생략)
    python -m collector.probe_topint --date 20260815
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):  # python collector/probe_topint.py 로도 실행 가능하게
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.auth import PosLoginError, create_session  # noqa: E402
from collector.config import Settings  # noqa: E402
from collector.logutil import enable_utf8_output, log, mask, section  # noqa: E402
from collector.pos_client import PosClient  # noqa: E402
from collector.probe_observer import Observation, Probe  # noqa: E402
from collector.probe_report import report_columns, report_menu_and_hour, report_summary  # noqa: E402

DATE_FORMAT = "%Y%m%d"
BACKFILL_PROBES = ((3, "back_3m"), (6, "back_6m"), (12, "back_12m"), (24, "back_24m"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POS 응답 실측 프로브 (STEP 1)")
    parser.add_argument("--date", help="기준일 YYYYMMDD (기본: 어제)")
    parser.add_argument("--quick", action="store_true", help="포맷/컬럼만 확인 (소급 프로브 생략)")
    return parser.parse_args()


def resolve_anchor(raw: str | None) -> date:
    if not raw:
        return date.today() - timedelta(days=1)
    return datetime.strptime(raw, DATE_FORMAT).date()


def print_environment(settings: Settings) -> None:
    section("환경")
    log(f"  POS_BASE_URL : {settings.pos_base_url}")
    log(f"  POS_BRANCH   : {settings.pos_branch or '(미설정)'}")
    log(f"  POS_USER_ID  : {mask(settings.pos_user_id, 3)}")
    log(f"  POS_USER_PW  : {mask(settings.pos_user_pw, 0)}")


def run_probes(probe: Probe, anchor: date, quick: bool) -> list[Observation]:
    observations: list[Observation] = []
    day = anchor.strftime(DATE_FORMAT)

    section("1. 단일일 조회 — 응답 포맷과 컬럼 구성 확인")
    single = probe.observe(day, day, "single_day")
    observations.append(single)

    if single.session_expired:
        log("\n세션이 만료되어 이후 프로브를 중단합니다.")
        log(".env의 POS_SESSION_COOKIE를 갱신하고 다시 실행하세요.")
        return observations

    section("2. 기간 조회 동작 — 7일을 주면 7행인가, 합계 1행인가")
    observations.append(
        probe.observe((anchor - timedelta(days=6)).strftime(DATE_FORMAT), day, "range_7d")
    )

    if quick:
        return observations

    observations.append(
        probe.observe((anchor - timedelta(days=29)).strftime(DATE_FORMAT), day, "range_30d")
    )

    section("3. 과거 소급 가능 범위")
    for months, label in BACKFILL_PROBES:
        past = (anchor - timedelta(days=30 * months)).strftime(DATE_FORMAT)
        observations.append(probe.observe(past, past, label))

    return observations


def main() -> int:
    enable_utf8_output()
    args = parse_args()
    settings = Settings.load()
    print_environment(settings)

    try:
        client = PosClient(settings, create_session(settings))
    except PosLoginError as error:
        log(f"\n{error}")
        return 1

    observations = run_probes(Probe(client, settings), resolve_anchor(args.date), args.quick)

    report_columns(observations)
    report_menu_and_hour(observations)
    report_summary(observations)

    log("\n원본 응답은 data/probe/ 에 있습니다 (gitignore 대상 — 커밋되지 않습니다).")
    log("관측 결과를 docs/03_POS_분석결과.md에 기록한 뒤 STEP 2로 넘어가세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
