"""
수동 수집 트리거 테스트 (FN-205 / FR-COL-07).

**POS에 실제 요청을 보내지 않는다.** 수집 본체와 GitHub API는 모두 대역으로 바꾼다.
확인하려는 것은 수집 자체가 아니라 「POS 서버 배려」 규칙을 지키는 차단 장치다:

  · 동시 실행 금지
  · 최소 간격 (연타·여러 탭)
  · 트리거 수단이 없는 환경에서는 아예 못 누르게

수집 파이프라인 자체는 test_aggregate / test_parse_* 가 검증한다.
"""

from __future__ import annotations

import dataclasses

import pytest

from collector.config import Settings
from server import collect_trigger


@pytest.fixture(autouse=True)
def reset_module_state():
    """모듈 전역 상태가 테스트 사이에 새지 않게 한다."""
    collect_trigger._local_run = None
    collect_trigger._local_last_start = None
    collect_trigger._dispatched_at = None
    yield
    collect_trigger._local_run = None
    collect_trigger._local_last_start = None
    collect_trigger._dispatched_at = None


def make_settings(**overrides) -> Settings:
    base = Settings(
        pos_user_id="", pos_user_pw="",
        dispatch_repo="", dispatch_token="",
        manual_collect_min_interval_sec=600,
    )
    return dataclasses.replace(base, **overrides)


# ── 백엔드 선택 ────────────────────────────────────────────

def test_backend_is_none_without_any_credentials():
    assert collect_trigger.backend_name(make_settings()) == "none"


def test_backend_is_local_with_pos_credentials():
    settings = make_settings(pos_user_id="id", pos_user_pw="pw")
    assert collect_trigger.backend_name(settings) == "local"


def test_backend_is_github_when_dispatch_configured():
    """배포 환경에서는 POS 계정이 없어도 Actions를 깨울 수 있어야 한다."""
    settings = make_settings(dispatch_repo="owner/repo", dispatch_token="ghp_x")
    assert collect_trigger.backend_name(settings) == "github"


def test_github_wins_when_both_configured():
    """둘 다 있으면 배포와 같은 경로를 타야 검증이 된다."""
    settings = make_settings(pos_user_id="id", pos_user_pw="pw",
                             dispatch_repo="owner/repo", dispatch_token="ghp_x")
    assert collect_trigger.backend_name(settings) == "github"


def test_unavailable_backend_reports_and_refuses():
    settings = make_settings()
    state = collect_trigger.state(settings, None, 1)
    assert (state.backend, state.available, state.running) == ("none", False, False)

    with pytest.raises(collect_trigger.Unavailable):
        collect_trigger.trigger(settings, None, 1)


# ── local — 최소 간격과 동시 실행 ──────────────────────────

def test_local_cooldown_blocks_second_press(monkeypatch):
    """DB에 방금 수집한 기록이 있으면 거절한다 (POS 서버 배려)."""
    settings = make_settings(pos_user_id="id", pos_user_pw="pw")
    monkeypatch.setattr(collect_trigger.system_repo, "last_collection_attempt",
                        lambda *_: collect_trigger._now_iso())

    state = collect_trigger.state(settings, None, 1)
    assert state.retry_after_sec > 0

    with pytest.raises(collect_trigger.TooSoon) as error:
        collect_trigger.trigger(settings, None, 1)
    assert error.value.retry_after_sec > 0
    assert "분 후에" in str(error.value)


def test_local_cooldown_expires(monkeypatch):
    settings = make_settings(pos_user_id="id", pos_user_pw="pw",
                             manual_collect_min_interval_sec=1)
    monkeypatch.setattr(collect_trigger.system_repo, "last_collection_attempt",
                        lambda *_: "2020-01-01T00:00:00+09:00")
    assert collect_trigger.state(settings, None, 1).retry_after_sec == 0


def test_local_cooldown_survives_a_run_that_logged_nothing(monkeypatch):
    """
    수집이 로그인 단계에서 실패하면 collection_logs 에 아무 행도 안 남는다.
    DB만 근거로 삼으면 그때 버튼을 누르는 대로 POS 로그인을 두드리게 된다.
    """
    settings = make_settings(pos_user_id="id", pos_user_pw="pw")
    monkeypatch.setattr(collect_trigger.system_repo, "last_collection_attempt",
                        lambda *_: None)
    monkeypatch.setattr(collect_trigger.threading, "Thread", _FakeThread)

    collect_trigger.trigger(settings, None, 1)
    collect_trigger._local_run.finished_at = collect_trigger._now_iso()   # 즉시 실패했다고 치고

    assert collect_trigger.state(settings, None, 1).retry_after_sec > 0
    with pytest.raises(collect_trigger.TooSoon):
        collect_trigger.trigger(settings, None, 1)


def test_local_refuses_while_running(monkeypatch):
    """탭을 여러 개 열어도 POS 요청은 한 번만 나가야 한다."""
    settings = make_settings(pos_user_id="id", pos_user_pw="pw",
                             manual_collect_min_interval_sec=0)
    monkeypatch.setattr(collect_trigger.system_repo, "last_collection_attempt",
                        lambda *_: None)
    monkeypatch.setattr(collect_trigger.threading, "Thread", _FakeThread)

    started = collect_trigger.trigger(settings, None, 1)
    assert started.running is True

    with pytest.raises(collect_trigger.AlreadyRunning):
        collect_trigger.trigger(settings, None, 1)


def test_local_worker_reports_failure_without_leaking_details(monkeypatch):
    """예외 내용에 계정·쿠키가 섞일 수 있다 — 화면 메시지에 실어 보내지 않는다."""
    settings = make_settings(pos_user_id="id", pos_user_pw="pw")

    def boom(_settings):
        raise RuntimeError("mem_pwd=super-secret cookie=comID=abc")

    monkeypatch.setattr("collector.scheduler.collect_yesterday", boom)

    run = collect_trigger._LocalRun(started_at=collect_trigger._now_iso())
    collect_trigger._local_worker(settings, run)

    assert run.ok is False
    assert run.finished_at is not None
    assert "RuntimeError" in run.message
    assert "secret" not in run.message and "comID" not in run.message


# ── github — Actions dispatch ──────────────────────────────

def github_settings(**overrides) -> Settings:
    return make_settings(dispatch_repo="owner/repo", dispatch_token="ghp_x",
                         dispatch_workflow="collect.yml", dispatch_ref="main",
                         **overrides)


def test_github_dispatch_marks_running(monkeypatch):
    calls = []

    def fake_request(method, path, settings, **kwargs):
        calls.append((method, path, kwargs.get("json")))
        return _FakeResponse(204)

    monkeypatch.setattr(collect_trigger, "_github_request", fake_request)

    state = collect_trigger.trigger(github_settings(), None, 1)
    assert (state.backend, state.running) == ("github", True)
    method, path, body = calls[-1]
    assert method == "POST"
    assert path.endswith("/actions/workflows/collect.yml/dispatches")
    assert body["ref"] == "main"


def test_github_dispatch_failure_becomes_trigger_error(monkeypatch):
    monkeypatch.setattr(collect_trigger, "_github_request",
                        lambda *a, **k: _FakeResponse(404))
    with pytest.raises(collect_trigger.TriggerError):
        collect_trigger.trigger(github_settings(), None, 1)


def test_github_state_reads_latest_run(monkeypatch):
    monkeypatch.setattr(collect_trigger, "_github_latest_run", lambda _s: {
        "status": "in_progress", "conclusion": None,
        "created_at": collect_trigger._now_iso(), "updated_at": None,
    })
    state = collect_trigger._github_state(github_settings())
    assert state.running is True
    assert state.ok is None


def test_github_completed_run_reports_cooldown(monkeypatch):
    monkeypatch.setattr(collect_trigger, "_github_latest_run", lambda _s: {
        "status": "completed", "conclusion": "success",
        "created_at": collect_trigger._now_iso(),
        "updated_at": collect_trigger._now_iso(),
    })
    state = collect_trigger._github_state(github_settings())
    assert state.running is False
    assert state.ok is True
    assert state.retry_after_sec > 0


def test_github_covers_the_gap_before_the_run_appears(monkeypatch):
    """
    dispatch 직후 몇 초간은 Actions 실행 목록에 아무것도 안 뜬다.
    그 구간에 running=False 를 돌려주면 화면이 '끝났다'고 오해한다.
    """
    monkeypatch.setattr(collect_trigger, "_github_request",
                        lambda *a, **k: _FakeResponse(204))
    monkeypatch.setattr(collect_trigger, "_github_latest_run", lambda _s: None)

    collect_trigger.trigger(github_settings(), None, 1)
    assert collect_trigger._github_state(github_settings()).running is True


def test_github_unreachable_does_not_crash(monkeypatch):
    def unreachable(_settings):
        raise collect_trigger.TriggerError("GitHub에 연결하지 못했습니다.")

    monkeypatch.setattr(collect_trigger, "_github_latest_run", unreachable)
    state = collect_trigger._github_state(github_settings())
    assert (state.running, state.ok) == (False, False)
    assert "GitHub" in state.message


# ── 대역 ───────────────────────────────────────────────────

class _FakeThread:
    """수집 스레드를 띄우지 않는다 — POS에 요청이 나가면 안 된다."""

    def __init__(self, *args, **kwargs):
        self.args = args

    def start(self):
        return None


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload
