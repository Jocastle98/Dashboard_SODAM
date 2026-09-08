"""
관측 결과 해석 — 가이드 STEP 1의 5개 확인 항목과 분기표를 코드로 옮긴 부분.

이 모듈은 판단 근거를 출력할 뿐 결론을 파일에 쓰지 않는다.
결론은 사람이 docs/03_POS_분석결과.md에 확정한다 (추측을 문서화하지 않기 위해).
"""

from __future__ import annotations

from .logutil import log, section
from .probe_observer import Observation

MENU_KEYWORDS = ("메뉴", "품목", "상품", "menu", "item")
HOUR_KEYWORDS = ("시간", "시간대", "hour", "시각")


def report_menu_and_hour(observations: list[Observation]) -> None:
    """확인 항목 5 — 메뉴별/시간대별 정보가 이 리포트에 포함되는가."""
    section("5. 메뉴별 / 시간대별 정보 포함 여부")

    columns = {column for obs in observations for column in obs.columns}
    if not columns:
        log("  컬럼을 추출하지 못해 판단 불가. data/probe/ 원본을 직접 확인하세요.")
        return

    menu_hits = sorted(c for c in columns if any(k in c for k in MENU_KEYWORDS))
    hour_hits = sorted(c for c in columns if any(k in c for k in HOUR_KEYWORDS))

    log(f"  메뉴 관련 컬럼 후보: {menu_hits or '없음'}")
    log(f"  시간대 관련 컬럼 후보: {hour_hits or '없음'}")
    if not menu_hits or not hour_hits:
        log("  → 없다면 POS에서 해당 리포트 화면을 찾아 URL을 추가 캡처해야 합니다")
        log("     (가이드 STEP 1 분기표 · FR-DASH-05/06 충족에 필요).")


def report_columns(observations: list[Observation]) -> None:
    """확인 항목 4 — 표의 실제 컬럼 구성을 하나도 빠짐없이 기록."""
    section("4. 실측 컬럼 구성 (docs/03에 그대로 옮길 것)")
    seen: set[tuple[str, ...]] = set()
    for obs in observations:
        if not obs.columns:
            continue
        key = tuple(obs.columns)
        if key in seen:
            continue
        seen.add(key)
        log(f"  [{obs.label}] {len(obs.columns)}개 컬럼")
        for index, column in enumerate(obs.columns):
            log(f"    {index:>2}. {column}")
    if not seen:
        log("  추출된 컬럼이 없습니다.")


def report_summary(observations: list[Observation]) -> None:
    section("요약 — docs/03_POS_분석결과.md에 옮겨 적을 것")
    log(f"{'라벨':<22}{'포맷':<10}{'행':>5}  {'상태':<6} 기간")
    log("-" * 68)
    for obs in observations:
        rows = obs.data_rows if obs.data_rows is not None else "?"
        fmt = obs.file_format or "-"
        log(f"{obs.label:<22}{fmt:<10}{str(rows):>5}  {obs.state_label:<6} "
            f"{obs.date_from}~{obs.date_to}")

    log()
    _report_period_branch(observations)
    _report_backfill_branch(observations)


def _report_period_branch(observations: list[Observation]) -> None:
    """확인 항목 2 → 가이드 분기표: 초기 12개월 적재 전략이 여기서 갈린다."""
    week = next((o for o in observations if o.label == "range_7d" and o.ok), None)
    if not week or week.data_rows is None:
        log("▶ 기간 조회 동작 미확인 — range_7d 관측이 없거나 행 수를 세지 못했습니다.")
        return

    if week.data_rows >= 5:
        log(f"▶ 7일 조회에 {week.data_rows}행 → 기간 조회로 여러 행이 나옵니다.")
        log("   초기 12개월 적재를 월 단위 12회 요청으로 처리하면 됩니다.")
    elif week.data_rows == 1:
        log("▶ 합계 1행만 나옵니다 → 일 단위 365회 순회 (1초 간격, 약 6분).")
    else:
        log(f"▶ 7일 조회에 {week.data_rows}행 — 원본을 직접 확인해 해석하세요.")


def _report_backfill_branch(observations: list[Observation]) -> None:
    """확인 항목 3 → SRS ASM-01(12개월 소급 가능 가정)의 검증."""
    reachable = [
        o for o in observations
        if o.label.startswith("back_") and o.ok and not o.session_expired and (o.data_rows or 0) > 0
    ]
    unreachable = [
        o for o in observations
        if o.label.startswith("back_") and o not in reachable
    ]

    if reachable:
        log(f"▶ 소급 확인 성공: {', '.join(o.label for o in reachable)}")
    if unreachable:
        log(f"▶ 소급 실패/빈 응답: {', '.join(o.label for o in unreachable)}")
    if not any(o.label == "back_12m" for o in reachable):
        log("   → SRS ASM-01(12개월 소급 가정)과 FR-COL-03을 재검토해야 합니다.")
        log("      확보 가능한 만큼만 적재하고 이후 누적하는 방향으로 범위 조정 (RSK-03).")
