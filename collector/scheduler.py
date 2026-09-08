"""
수집 스케줄러 (FN-601 / FR-COL-01) — 매일 정해진 시각에 전일 데이터를 수집한다.

수집 자체는 `service.Collector`가 한다. 여기서는 '언제 돌릴지'와
'실패하면 어떻게 알릴지'만 다룬다.

앱 안에서 돌릴 수도 있고(`server.main`), 독립 프로세스로 돌릴 수도 있다:
    python -m collector.scheduler          # 상주 실행
    python -m collector.scheduler --once   # 지금 1회 실행 (검증용)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

from collector import repository as repo  # noqa: E402
from collector.auth import create_session  # noqa: E402
from collector.config import Settings  # noqa: E402
from collector.logutil import enable_utf8_output, log, section, warn  # noqa: E402
from collector.notify import notify_failure  # noqa: E402
from collector.pos_client import PosClient  # noqa: E402
from collector.service import Collector  # noqa: E402

JOB_ID = "daily_collect"


def collect_yesterday(settings: Settings) -> bool:
    """
    전일 1일치를 수집한다. 성공 여부를 돌려준다.
    실패해도 예외를 밖으로 던지지 않는다 — 스케줄러가 죽으면 다음 날도 안 돈다.
    """
    target = date.today() - timedelta(days=1)
    section(f"자동 수집 {target}")

    try:
        with repo.connect(settings) as session:
            repo.apply_schema(session)
            client = PosClient(settings, create_session(settings))
            result = Collector(settings, client, session).collect(target, target)
    except Exception as error:  # noqa: BLE001 — 어떤 실패든 알리고 살아남는다
        warn(f"수집 중단: {type(error).__name__}: {error}")
        notify_failure(settings, f"{target} 수집 실패", f"{type(error).__name__}: {error}")
        return False

    log(f"  주문 {result.orders}건 / 메뉴 {result.menu_rows}행 / 취소 {result.cancels}건")

    if result.failures:
        notify_failure(
            settings, f"{target} 수집 일부 실패",
            "\n".join(result.failures[:10]),
        )
        return False

    if result.issues:
        notify_failure(
            settings, f"{target} 데이터 품질 경고",
            "\n".join(f"[{i.rule}] {i.biz_date} {i.message}" for i in result.issues[:10]),
        )

    log("  수집 완료")
    return True


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    """매일 `COLLECT_HOUR`시(기본 04시, Asia/Seoul)에 전일 데이터를 수집한다."""
    scheduler = BackgroundScheduler(timezone=settings.collect_tz)
    scheduler.add_job(
        collect_yesterday,
        trigger=CronTrigger(hour=settings.collect_hour, minute=0, timezone=settings.collect_tz),
        args=[settings],
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,   # 서버가 잠깐 죽어 있었어도 1시간 안이면 따라잡는다
        coalesce=True,             # 밀린 실행을 한 번으로 합친다
        max_instances=1,           # 겹쳐 돌지 않게 — POS에 동시 요청 금지
    )
    return scheduler


def describe(settings: Settings) -> str:
    return f"매일 {settings.collect_hour:02d}:00 ({settings.collect_tz}) 전일 데이터 수집"


def main() -> int:
    enable_utf8_output()
    settings = Settings.load()

    if "--once" in sys.argv:
        return 0 if collect_yesterday(settings) else 2

    section("스케줄러 시작")
    log(f"  {describe(settings)}")
    scheduler = build_scheduler(settings)
    scheduler.start()
    log(f"  다음 실행: {scheduler.get_job(JOB_ID).next_run_time}")
    log("  종료하려면 Ctrl+C")

    try:
        import time
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log("\n스케줄러를 종료했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
