"""
수동 수집 트리거 (FN-205 / FR-COL-07).

사장님이 화면 버튼을 누르면 POS에서 지금 데이터를 받아온다.

**환경에 따라 수집을 실행하는 주체가 다르다.** 그 판단을 여기 한 곳에서만 한다 —
라우터와 프론트엔드는 어느 백엔드인지 몰라도 된다.

    local  이 프로세스가 백그라운드 스레드에서 직접 수집한다 (내 PC·자체 서버).
    github GitHub Actions를 깨운다 (Vercel 배포).
           Vercel 함수는 10초에서 끊기지만 수집은 30초~1분 걸린다.
           게다가 Vercel에는 POS 계정을 두지 않는다 (CLAUDE.md 보안 규칙) —
           그러니 Vercel은 "수집해달라"고 부탁만 하고 빠진다.
    none   트리거할 수단이 없다. 화면은 버튼을 숨긴다.

「POS 서버 배려」 규칙이 버튼 하나 때문에 깨지지 않게 두 겹으로 막는다.

    1. 동시 실행 금지 — 탭을 여러 개 열어도 POS 요청은 한 번만 나간다.
    2. 최소 간격      — 마지막 수집으로부터 `MANUAL_COLLECT_MIN_INTERVAL_SEC`
                        안에는 거절한다 (기본 10분).

두 겹 다 **프로세스 메모리에만 의존하지 않는다.** local은 DB의 수집 이력을,
github은 Actions 실행 목록을 근거로 삼는다 — Vercel처럼 인스턴스가 여러 개여도
같은 판단이 나와야 하기 때문이다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from collector.config import Settings

from .repository import system as system_repo
from collector.db import Session

GITHUB_API = "https://api.github.com"
HTTP_TIMEOUT_SEC = 5          # Vercel 함수가 10초에서 끊긴다 — 넉넉히 잡을 수 없다
DISPATCH_GRACE_SEC = 90       # dispatch 직후 실행 목록에 아직 안 뜨는 구간
RUNNING_STATUSES = ("queued", "in_progress", "requested", "waiting", "pending")


class TriggerError(Exception):
    """트리거 실패 — 라우터가 상태코드로 옮긴다."""


class Unavailable(TriggerError):
    """트리거할 수단이 없다 (POS 계정도, DISPATCH_* 도 없음)."""


class AlreadyRunning(TriggerError):
    """이미 수집이 돌고 있다."""


class TooSoon(TriggerError):
    """최소 간격 안에 다시 눌렀다."""

    def __init__(self, retry_after_sec: int):
        super().__init__(_cooldown_message(retry_after_sec))
        self.retry_after_sec = retry_after_sec


@dataclass(frozen=True)
class TriggerState:
    """화면이 버튼을 어떻게 그릴지 결정하는 데 필요한 전부."""

    backend: str
    available: bool
    running: bool
    started_at: str | None = None
    finished_at: str | None = None
    ok: bool | None = None
    message: str = ""
    retry_after_sec: int = 0

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "available": self.available,
            "running": self.running,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "ok": self.ok,
            "message": self.message,
            "retryAfterSec": self.retry_after_sec,
        }


# ── 백엔드 선택 ────────────────────────────────────────────

def backend_name(settings: Settings) -> str:
    """
    github이 우선이다. 둘 다 설정된 환경(내 PC에서 배포 설정을 켜 둔 경우)에서는
    실제 배포와 같은 경로를 타는 편이 검증에 유리하다.
    """
    if settings.dispatch_repo and settings.dispatch_token:
        return "github"
    if settings.pos_user_id and settings.pos_user_pw:
        return "local"
    return "none"


def state(settings: Settings, session: Session, store_id: int) -> TriggerState:
    """GET /api/system/collect/status 의 내용."""
    backend = backend_name(settings)
    if backend == "local":
        return _local_state(settings, session, store_id)
    if backend == "github":
        return _github_state(settings)
    return TriggerState(
        backend="none", available=False, running=False,
        message="이 환경에서는 수동 수집을 쓸 수 없습니다.",
    )


def trigger(settings: Settings, session: Session, store_id: int) -> TriggerState:
    """
    POST /api/system/collect — 수집을 시작시킨다.

    이미 돌고 있거나 최소 간격 안이면 예외를 던진다. POS에 요청이 겹쳐 나가는 것을
    막는 게 목적이므로 거절이 정상 동작이다.
    """
    current = state(settings, session, store_id)
    if not current.available:
        raise Unavailable("이 환경에서는 수동 수집을 쓸 수 없습니다.")
    if current.running:
        raise AlreadyRunning("이미 수집이 진행 중입니다.")
    if current.retry_after_sec > 0:
        raise TooSoon(current.retry_after_sec)

    if current.backend == "local":
        return _local_start(settings)
    return _github_start(settings)


# ── local — 이 프로세스가 직접 수집한다 ─────────────────────
#
# 스레드 하나만 띄운다. 진행 상태는 메모리에 두지만 **최소 간격 판단은 DB를 본다** —
# 서버를 재시작해도, 04시 스케줄러가 방금 돌았어도 간격이 지켜져야 한다.

@dataclass
class _LocalRun:
    started_at: str
    finished_at: str | None = None
    ok: bool | None = None
    message: str = "수집 중입니다."


_local_lock = threading.Lock()
_local_run: _LocalRun | None = None
# 마지막 시작 시각을 따로 들고 있는다. DB 로그는 첫 리포트 요청이 끝난 뒤에야 쓰이므로,
# 로그인 단계에서 바로 실패하면 collection_logs 에 아무것도 남지 않는다.
# 그것만 근거로 삼으면 실패할 때 버튼을 누르는 대로 POS 로그인을 두드리게 된다.
_local_last_start: datetime | None = None


def _local_state(settings: Settings, session: Session,
                 store_id: int) -> TriggerState:
    run = _local_run
    running = run is not None and run.finished_at is None
    return TriggerState(
        backend="local",
        available=True,
        running=running,
        started_at=run.started_at if run else None,
        finished_at=run.finished_at if run else None,
        ok=run.ok if run else None,
        message=run.message if run else "",
        retry_after_sec=0 if running else _cooldown_sec(settings, session, store_id),
    )


def _local_start(settings: Settings) -> TriggerState:
    global _local_run, _local_last_start

    with _local_lock:
        if _local_run is not None and _local_run.finished_at is None:
            raise AlreadyRunning("이미 수집이 진행 중입니다.")
        _local_run = _LocalRun(started_at=_now_iso())
        _local_last_start = _now()
        run = _local_run

    threading.Thread(target=_local_worker, args=(settings, run),
                     name="manual-collect", daemon=True).start()
    return TriggerState(backend="local", available=True, running=True,
                        started_at=run.started_at, message=run.message)


def _local_worker(settings: Settings, run: _LocalRun) -> None:
    """
    실제 수집은 `collector.scheduler.collect_yesterday()`가 한다 —
    스케줄러와 수동 버튼이 같은 경로를 타야 한쪽만 고쳐지는 일이 없다.
    """
    from collector.scheduler import collect_yesterday

    try:
        ok = collect_yesterday(settings)
        run.ok = ok
        run.message = (
            "수집을 마쳤습니다." if ok
            else "수집에 실패했습니다. 잠시 후 다시 시도해 주세요."
        )
    except Exception as error:                          # noqa: BLE001
        run.ok = False
        # 예외 내용에 계정·쿠키가 섞일 수 있다 — 화면에는 종류만 내보낸다
        run.message = f"수집에 실패했습니다. ({type(error).__name__})"
    finally:
        run.finished_at = _now_iso()


def _cooldown_sec(settings: Settings, session: Session, store_id: int) -> int:
    """
    마지막 수집 **시도** 시각을 기준으로 남은 대기 시간. 성공만 보면
    실패가 반복될 때 POS를 계속 두드리게 된다.
    """
    interval = settings.manual_collect_min_interval_sec
    if interval <= 0:
        return 0

    last = system_repo.last_collection_attempt(session, store_id)
    candidates = [moment for moment in (_parse_iso(last) if last else None, _local_last_start)
                  if moment is not None]
    if not candidates:
        return 0
    return max(0, int(interval - (_now() - max(candidates)).total_seconds()))


# ── github — Actions를 깨운다 ──────────────────────────────

def _github_state(settings: Settings) -> TriggerState:
    """
    최근 실행 1건으로 판단한다. Actions는 dispatch 직후 몇 초간 실행 목록에
    나타나지 않으므로, 방금 부탁한 건은 `_dispatched_at`으로 메워 준다.
    """
    try:
        run = _github_latest_run(settings)
    except TriggerError as error:
        return TriggerState(backend="github", available=True, running=False,
                            ok=False, message=str(error))

    if run is None:
        return TriggerState(backend="github", available=True,
                            running=_within_dispatch_grace(),
                            message="수집 이력이 없습니다.")

    running = run.get("status") in RUNNING_STATUSES
    if not running and _within_dispatch_grace(after=run.get("created_at")):
        running = True                      # 방금 부탁한 건이 아직 목록에 안 뜬 상태

    conclusion = run.get("conclusion")
    return TriggerState(
        backend="github",
        available=True,
        running=running,
        started_at=run.get("created_at"),
        finished_at=None if running else run.get("updated_at"),
        ok=None if running else (conclusion == "success"),
        message=(
            "수집 중입니다." if running
            else "수집을 마쳤습니다." if conclusion == "success"
            else f"수집에 실패했습니다. ({conclusion})"
        ),
        retry_after_sec=0 if running else _github_cooldown_sec(settings, run.get("created_at")),
    )


def _github_start(settings: Settings) -> TriggerState:
    global _dispatched_at

    response = _github_request(
        "POST",
        f"/repos/{settings.dispatch_repo}/actions/workflows"
        f"/{settings.dispatch_workflow}/dispatches",
        settings,
        json={"ref": settings.dispatch_ref, "inputs": {"reason": "dashboard-button"}},
    )
    if response.status_code != 204:
        raise TriggerError(f"수집을 시작하지 못했습니다. (GitHub {response.status_code})")

    _dispatched_at = _now()
    return TriggerState(backend="github", available=True, running=True,
                        started_at=_now_iso(), message="수집을 요청했습니다.")


def _github_latest_run(settings: Settings) -> dict | None:
    response = _github_request(
        "GET",
        f"/repos/{settings.dispatch_repo}/actions/workflows"
        f"/{settings.dispatch_workflow}/runs?per_page=1",
        settings,
    )
    if response.status_code != 200:
        raise TriggerError(f"수집 상태를 확인하지 못했습니다. (GitHub {response.status_code})")
    runs = response.json().get("workflow_runs") or []
    return runs[0] if runs else None


def _github_request(method: str, path: str, settings: Settings, **kwargs):
    import requests

    try:
        return requests.request(
            method, GITHUB_API + path,
            headers={
                "Authorization": f"Bearer {settings.dispatch_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=HTTP_TIMEOUT_SEC, **kwargs,
        )
    except requests.RequestException as error:
        raise TriggerError(f"GitHub에 연결하지 못했습니다. ({type(error).__name__})") from error


def _github_cooldown_sec(settings: Settings, created_at: str | None) -> int:
    interval = settings.manual_collect_min_interval_sec
    moment = _parse_iso(created_at) if created_at else None
    if interval <= 0 or moment is None:
        return 0
    return max(0, int(interval - (_now() - moment).total_seconds()))


_dispatched_at: datetime | None = None


def _within_dispatch_grace(after: str | None = None) -> bool:
    """
    이 인스턴스가 방금 dispatch 했고 아직 유예 시간 안인가.
    Vercel처럼 인스턴스가 여러 개면 다른 인스턴스의 dispatch는 알 수 없다 —
    그때는 Actions 실행 목록에 뜨는 것으로 잡힌다.
    """
    if _dispatched_at is None:
        return False
    if (_now() - _dispatched_at) > timedelta(seconds=DISPATCH_GRACE_SEC):
        return False
    if after is None:
        return True
    moment = _parse_iso(after)
    return moment is None or moment < _dispatched_at


# ── 표현·시각 처리 ─────────────────────────────────────────

def _cooldown_message(seconds: int) -> str:
    """POS 서버 배려 규칙 때문에 거절했다는 것을 사장님 말로 설명한다."""
    if seconds >= 60:
        return f"방금 수집했습니다. 약 {seconds // 60}분 후에 다시 누를 수 있습니다."
    return f"방금 수집했습니다. {seconds}초 후에 다시 누를 수 있습니다."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().astimezone().isoformat(timespec="seconds")


def _parse_iso(text: str) -> datetime | None:
    """DB는 오프셋 포함 ISO, GitHub은 `...Z`로 준다. 둘 다 받는다."""
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
